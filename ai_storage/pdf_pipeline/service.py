"""Trusted CLI orchestration. Slow OCR/embedding never holds a database transaction."""
from contextlib import contextmanager
from datetime import timedelta
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
import uuid

from django.conf import settings
from django.db import DatabaseError, close_old_connections, transaction
from django.db.models import Max, Q
from django.utils import timezone

from ai_storage.embeddings import embed_texts
from ai_storage.models import EmbeddingSpace, KnowledgeChunk, KnowledgeDocument, KnowledgeImportJob, KnowledgePage
from .chunking import CHUNKER_VERSION, make_chunks
from .parser import PARSER_VERSION
from .storage import file_digest, job_path, store_pdf

DB = 'ai_storage'
LEASE_SECONDS = 180


class LeaseLost(RuntimeError):
    pass


def operator(actor_id):
    from users.models import UserProfile
    from users.access import account_access, can_access_platform
    actor = UserProfile.objects.filter(pk=actor_id, is_active=True).first()
    if actor is None or not can_access_platform(account_access(actor), 'system_config'):
        raise ValueError('An active platform operator with system_config permission is required')
    return actor


def tokenizer_path():
    path = Path(os.getenv('AI_PDF_TOKENIZER_PATH', '/models/bge-m3/tokenizer.json'))
    if not path.is_file():
        raise ValueError('Install the pinned BGE-M3 tokenizer and set AI_PDF_TOKENIZER_PATH')
    return path


def pipeline_config(languages, ocr_mode, vision_mode='off', vision_tasks=None,
                    document_backend='legacy', document_mode='auto'):
    if languages not in ('eng', 'chi_sim', 'ara', 'chi_sim+eng', 'ara+eng', 'chi_sim+eng+ara'):
        raise ValueError('Unsupported OCR language set')
    if ocr_mode not in ('auto', 'force'):
        raise ValueError('OCR mode must be auto or force')
    if settings.AI_OLLAMA_MODEL != 'bge-m3':
        raise ValueError('This chunk tokenizer is configured for bge-m3; configure a matching pipeline before changing models')
    from ai_storage.vision.config import freeze
    from .paddleocr import freeze as freeze_document
    if document_backend != 'legacy' and vision_mode != 'off':
        raise ValueError('Document backend and optional vision tasks must be submitted separately')
    document = freeze_document(document_backend, document_mode)
    return {'parser': PARSER_VERSION, 'chunker': CHUNKER_VERSION, 'vision': freeze(vision_mode, vision_tasks),
        'document_parser': document,
        'languages': languages, 'ocr_mode': ocr_mode, 'dpi': 200, 'max_pixels': 24000000,
        'max_pages': 200, 'max_bytes': 50 * 1024 * 1024, 'ocr_timeout': 45,
        'min_confidence': 70, 'target_tokens': 500, 'max_tokens': 800, 'overlap_tokens': 64,
        'embedding_batch': 8, 'embedding_model': settings.AI_OLLAMA_MODEL,
        'embedding_revision': settings.AI_OLLAMA_REVISION, 'space_key': settings.AI_EMBEDDING_SPACE_KEY,
        'tokenizer_sha256': file_digest(tokenizer_path())}


def enqueue(path, actor_id, title, source_key, visibility='private', owner_id=None,
            languages='chi_sim+eng', ocr_mode='auto', vision_mode='off', vision_tasks=None,
            document_backend='legacy', document_mode='auto'):
    operator(actor_id)
    if visibility not in ('private', 'public') or not title.strip() or len(title) > 255 or not source_key or len(source_key) > 200:
        raise ValueError('Invalid title, source key or visibility')
    if visibility == 'private':
        from users.models import UserProfile
        owner_id = owner_id or actor_id
        if not UserProfile.objects.filter(pk=owner_id, is_active=True).exists():
            raise ValueError('Private owner does not exist or is inactive')
    elif owner_id is not None:
        raise ValueError('A public document must not carry a private owner')
    config = pipeline_config(languages, ocr_mode, vision_mode, vision_tasks, document_backend, document_mode)
    if document_backend == 'paddleocr':
        config['max_pixels'] = 6000000
    identity = uuid.uuid4()
    checksum = store_pdf(path, identity, config['max_bytes'])
    # Identity and ACL participate in deduplication; never reuse another owner's artifact.
    scope = {'actor': actor_id, 'owner': owner_id, 'visibility': visibility, 'source': source_key}
    fingerprint = hashlib.sha256(json.dumps({'scope': scope, 'file': checksum, 'title': title, 'config': config},
        sort_keys=True).encode('utf8')).hexdigest()
    series = 'pdf:{}:{}'.format(actor_id, hashlib.sha256(json.dumps(scope, sort_keys=True).encode()).hexdigest())
    try:
        with transaction.atomic(using=DB):
            # A transaction-scoped series lock also serializes the very first version.
            from django.db import connections
            with connections[DB].cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(hashlib.sha256(series.encode()).hexdigest()[:15], 16)])
            existing = KnowledgeImportJob.objects.filter(fingerprint=fingerprint).first()
            if existing:
                job_path(identity).unlink()
                job_path(identity).parent.rmdir()
                return existing
            version = (KnowledgeDocument.objects.filter(source_key=series).aggregate(n=Max('version'))['n'] or 0) + 1
            document = KnowledgeDocument.objects.create(source_key=series, version=version, title=title,
                visibility=visibility, owner_id=owner_id, status='draft',
                metadata={'source_type': 'pdf', 'file_sha256': checksum, 'submitted_source_key': source_key})
            document.source_reference = '/v1/support/knowledge/documents/{}/file'.format(document.pk)
            document.save(update_fields=['source_reference'])
            return KnowledgeImportJob.objects.create(id=identity, document=document, actor_id=actor_id,
                fingerprint=fingerprint, file_sha256=checksum, config=config)
    except Exception:
        # Only the fresh UUID's file is removed, never a recursive/shared directory.
        job_path(identity).unlink(missing_ok=True)
        if job_path(identity).parent.exists():
            job_path(identity).parent.rmdir()
        raise


def claim(job_id=None):
    with transaction.atomic(using=DB):
        eligible = KnowledgeImportJob.objects.select_for_update(skip_locked=True).filter(
            Q(status='queued') | Q(status='running', lease_until__lt=timezone.now())).order_by('created_at')
        if job_id:
            eligible = eligible.filter(pk=job_id)
        job = eligible.first()
        if not job:
            return None
        if job.document.status != 'draft':
            raise ValueError('Only draft imports may be processed')
        job.status, job.lease_token = 'running', uuid.uuid4()
        job.lease_until = timezone.now() + timedelta(seconds=LEASE_SECONDS)
        job.attempt += 1
        job.error_code = ''
        job.save()
        return job


@contextmanager
def owned(job):
    with transaction.atomic(using=DB):
        current = KnowledgeImportJob.objects.select_for_update().get(pk=job.pk)
        if current.status != 'running' or current.lease_token != job.lease_token or current.lease_until <= timezone.now():
            raise LeaseLost('Import lease lost')
        yield current
        current.updated_at = timezone.now()
        current.save()


@contextmanager
def heartbeat(job):
    stop = threading.Event()
    def renew():
        while not stop.wait(20):
            try:
                KnowledgeImportJob.objects.filter(pk=job.pk, status='running', lease_token=job.lease_token,
                    lease_until__gt=timezone.now()).update(lease_until=timezone.now() + timedelta(seconds=LEASE_SECONDS))
            except DatabaseError:
                return  # Let the lease expire; never log private database errors.
            finally:
                close_old_connections()
    thread = threading.Thread(target=renew, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stop.set()
        thread.join(timeout=5)


def _parse(job, number, preview, vision_preview=None):
    # Parent owns temporary cleanup, including when the parser is force-killed.
    with tempfile.TemporaryDirectory(prefix='knowledge-page-') as folder:
        env = dict(os.environ, TMPDIR=folder, TEMP=folder, TMP=folder)
        env.pop('AI_VISION_API_KEY', None)
        env.pop('AI_PADDLEOCR_API_KEY', None)
        return _parse_process(job, number, preview, env, vision_preview)


def _parse_process(job, number, preview, env, vision_preview=None):
    config = dict(job.config)
    if vision_preview is not None:
        config['vision_render_path'] = str(vision_preview)
    args = [sys.executable, '-m', 'ai_storage.pdf_pipeline.parser', str(job_path(job.pk)),
            str(number), str(preview), json.dumps(config)]
    process = subprocess.Popen(args, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=os.name != 'nt')
    try:
        stdout, stderr = process.communicate(timeout=120)
    except subprocess.TimeoutExpired:
        if os.name != 'nt':
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
        process.communicate()
        raise TimeoutError('PDF page processing timeout') from None
    if process.returncode:
        raise ValueError('PDF_PARSE_OR_OCR_FAILED')
    return json.loads(stdout)


def process(job):
    vision = None
    document_parser = None
    try:
        with heartbeat(job):
            if (job.config.get('parser') != PARSER_VERSION
                    or job.config.get('chunker') != CHUNKER_VERSION):
                from .page_ir import DocumentError
                raise DocumentError('DOCUMENT_PIPELINE_CHANGED')
            snapshot = job.config.get('vision', {'mode': 'off'})
            document_snapshot = job.config.get('document_parser', {'backend': 'legacy'})
            if document_snapshot.get('backend') == 'paddleocr':
                from .paddleocr import PaddlePageProcessor
                from .storage import root
                namespace = '{}:{}:{}'.format(job.document.visibility, job.document.owner_id, job.actor_id)
                document_parser = PaddlePageProcessor(document_snapshot,
                    cache_root=root() / '.document-cache-v1', namespace=namespace)
            if snapshot.get('mode', 'off') != 'off':
                from ai_storage.vision.pipeline import VisionPageProcessor
                from .storage import root
                document = job.document
                namespace = '{}:{}:{}'.format(document.visibility, document.owner_id, job.actor_id)
                vision = VisionPageProcessor(snapshot, cache_root=root() / '.vision-cache-v1', namespace=namespace)
            if file_digest(job_path(job.pk)) != job.file_sha256:
                raise ValueError('SOURCE_HASH_MISMATCH')
            if file_digest(tokenizer_path()) != job.config['tokenizer_sha256']:
                raise ValueError('TOKENIZER_CHANGED')
            if (settings.AI_OLLAMA_MODEL, settings.AI_OLLAMA_REVISION, settings.AI_EMBEDDING_SPACE_KEY) != (
                    job.config['embedding_model'], job.config['embedding_revision'], job.config['space_key']):
                raise ValueError('EMBEDDING_CONFIG_CHANGED')
            info = _parse(job, 0, '')
            with owned(job) as current:
                previous_runtime = current.document.metadata.get('parser_runtime')
                if previous_runtime and previous_runtime != info:
                    raise ValueError('PARSER_RUNTIME_CHANGED')
                current.stage, current.total_pages = 'extracting', info['total_pages']
                metadata = dict(current.document.metadata, parser_runtime=info)
                KnowledgeDocument.objects.filter(pk=job.document_id).update(metadata=metadata)
            for number in range(1, info['total_pages'] + 1):
                if (KnowledgePage.objects.filter(document_id=job.document_id, number=number, status='ready').exists()
                        and job_path(job.pk, 'page-{}.png'.format(number)).is_file()):
                    continue
                temporary = job_path(job.pk, 'page-{}.png'.format(number)).with_name('{}-{}.png'.format(number, job.lease_token))
                vision_temporary = temporary.with_name('vision-' + temporary.name) if vision or document_parser else None
                try:
                    with owned(job) as current:
                        current.stage = 'extracting'
                    result = _parse(job, number, temporary, vision_temporary) if vision or document_parser else _parse(job, number, temporary)
                    if document_parser:
                        with owned(job) as current:
                            current.stage = 'recognizing'
                        result = document_parser.process(result, vision_temporary.read_bytes())
                    if vision:
                        # 外部模型等待期间不持有事务；返回后再次通过 owned 栅栏检查。
                        with owned(job):
                            pass
                        result = vision.process(result, vision_temporary.read_bytes())
                    with owned(job) as current:
                        os.replace(str(temporary), str(job_path(job.pk, 'page-{}.png'.format(number))))
                        KnowledgePage.objects.update_or_create(document_id=job.document_id, number=number,
                            defaults={k: result[k] for k in ('width', 'height', 'rotation', 'blocks', 'method', 'warnings')})
                        KnowledgePage.objects.filter(document_id=job.document_id, number=number).update(status='ready', error_code='')
                        current.processed_pages = KnowledgePage.objects.filter(document_id=job.document_id, status='ready').count()
                except LeaseLost:
                    raise
                except Exception as exc:
                    with owned(job):
                        KnowledgePage.objects.update_or_create(document_id=job.document_id, number=number,
                            defaults={'status': 'failed', 'error_code': type(exc).__name__})
                    raise
                finally:
                    temporary.unlink(missing_ok=True)
                    if vision_temporary is not None:
                        vision_temporary.unlink(missing_ok=True)
            pages = list(KnowledgePage.objects.filter(document_id=job.document_id).order_by('number'))
            warnings = [{'page': page.number, 'codes': page.warnings} for page in pages if page.warnings]
            with owned(job) as current:
                current.stage, current.warnings = 'quality_checking', warnings
            if any(code.startswith('document_blocking_') for page in pages for code in page.warnings):
                from .page_ir import DocumentError
                raise DocumentError('DOCUMENT_REVIEW_REQUIRED')
            if any(code.startswith('vision_blocking_') for page in pages for code in page.warnings):
                raise ValueError('VISION_REVIEW_REQUIRED')
            from tokenizers import Tokenizer
            with owned(job) as current:
                current.stage = 'chunking'
            tokenizer = Tokenizer.from_file(str(tokenizer_path()))
            chunks = make_chunks(pages, tokenizer, job.config['target_tokens'], job.config['max_tokens'], job.config['overlap_tokens'])
            if not chunks:
                raise ValueError('NO_USABLE_TEXT')
            with owned(job) as current:
                current.stage, current.warnings = 'embedding', warnings
                # Deterministic rebuild; unchanged vectors survive a retry.
                for ordinal, chunk in enumerate(chunks):
                    stored = KnowledgeChunk.objects.filter(document_id=job.document_id, ordinal=ordinal).first()
                    if stored and stored.text == chunk['text'] and stored.metadata == chunk['metadata']:
                        continue
                    KnowledgeChunk.objects.update_or_create(document_id=job.document_id, ordinal=ordinal,
                        defaults={**chunk, 'embedding': None, 'embedding_space': None})
                KnowledgeChunk.objects.filter(document_id=job.document_id, ordinal__gte=len(chunks)).delete()
            pending = KnowledgeChunk.objects.filter(document_id=job.document_id, embedding__isnull=True).order_by('ordinal')
            while True:
                batch = list(pending[:job.config['embedding_batch']])
                if not batch:
                    break
                vectors = embed_texts([chunk.text for chunk in batch], timeout=(5, 60))
                dimensions = len(vectors[0])
                if any(len(v) != dimensions or not any(v) or any(type(x) not in (float, int) or not math.isfinite(x) for x in v) for v in vectors):
                    raise ValueError('INVALID_EMBEDDING')
                with owned(job):
                    space, created = EmbeddingSpace.objects.get_or_create(key=job.config['space_key'], defaults={
                        'provider': 'ollama', 'model': job.config['embedding_model'],
                        'revision': job.config['embedding_revision'], 'dimensions': dimensions})
                    if (space.provider, space.model, space.revision, space.dimensions) != (
                            'ollama', job.config['embedding_model'], job.config['embedding_revision'], dimensions):
                        raise ValueError('EMBEDDING_SPACE_MISMATCH')
                    for chunk, vector in zip(batch, vectors):
                        chunk.embedding, chunk.embedding_space = vector, space
                        chunk.save(update_fields=['embedding', 'embedding_space'])
            with owned(job) as current:
                current.status, current.stage = 'awaiting_review', 'review'
                current.lease_until, current.lease_token = None, None
                if document_parser:
                    metadata = dict(current.document.metadata, document_parser_summary={
                        'provider': 'paddleocr', 'provider_attempts': document_parser.calls,
                        'processed_pages': document_parser.pages, 'cache_hits': document_parser.hits,
                        'model': document_parser.config.model, 'revision': document_parser.config.revision})
                    KnowledgeDocument.objects.filter(pk=job.document_id).update(metadata=metadata)
                if vision:
                    metadata = dict(current.document.metadata, vision_summary={
                        'provider_attempts': vision.calls, 'processed_pages': vision.pages, 'cache_hits': vision.hits,
                        'model': vision.config.model, 'revision': vision.config.revision})
                    KnowledgeDocument.objects.filter(pk=job.document_id).update(metadata=metadata)
    except LeaseLost:
        return
    except Exception as exc:
        from ai_storage.vision.contracts import VisionError
        from .page_ir import DocumentError
        detail = str(exc) if isinstance(exc, (VisionError, DocumentError)) else (str(exc) if str(exc) in (
                'SOURCE_HASH_MISMATCH', 'TOKENIZER_CHANGED', 'EMBEDDING_CONFIG_CHANGED', 'NO_USABLE_TEXT',
                'INVALID_EMBEDDING', 'EMBEDDING_SPACE_MISMATCH', 'PDF_PARSE_OR_OCR_FAILED', 'PARSER_RUNTIME_CHANGED',
                'VISION_REVIEW_REQUIRED', 'VISION_TABLE_TEXT_MISMATCH', 'VISION_TABLE_ROW_TOO_LARGE') else 'pipeline_error')
        KnowledgeImportJob.objects.filter(pk=job.pk, status='running', lease_token=job.lease_token).update(
            status='failed', error_code=(type(exc).__name__ + ':' + detail)[:60],
            lease_until=None, lease_token=None, updated_at=timezone.now())
    finally:
        if vision:
            vision.close()
        if document_parser:
            document_parser.close()


def action(job_id, actor_id, verb, accept_warnings=False):
    operator(actor_id)
    with transaction.atomic(using=DB):
        job = KnowledgeImportJob.objects.select_for_update().select_related('document').get(pk=job_id)
        document = job.document
        if verb == 'retry':
            if job.status not in ('failed', 'cancelled') or document.status != 'draft':
                raise ValueError('Only failed or cancelled drafts may be retried')
            job.status, job.error_code = 'queued', ''
        elif verb == 'cancel':
            if job.status not in ('queued', 'running', 'failed', 'awaiting_review'):
                raise ValueError('This import cannot be cancelled')
            job.status = 'cancelled'
            job.lease_token, job.lease_until = None, None
        elif verb == 'publish':
            if job.status != 'awaiting_review' or document.status != 'draft':
                raise ValueError('Import is not ready for review')
            if job.warnings and not accept_warnings:
                raise ValueError('Review page warnings, then explicitly use --accept-warnings')
            if any(code.startswith(('vision_blocking_', 'document_blocking_')) for codes in
                   KnowledgePage.objects.filter(document=document).values_list('warnings', flat=True) for code in codes):
                raise ValueError('Unresolved visual extraction problems block publication')
            if file_digest(job_path(job.pk)) != job.file_sha256:
                raise ValueError('Source PDF integrity check failed')
            if any(not job_path(job.pk, 'page-{}.png'.format(number)).is_file()
                   for number in range(1, job.total_pages + 1)):
                raise ValueError('Page previews are missing; cancel and retry the draft to regenerate')
            if (job.processed_pages != job.total_pages or not job.total_pages or
                    KnowledgePage.objects.filter(document=document).exclude(status='ready').exists() or
                    not KnowledgeChunk.objects.filter(document=document).exists() or
                    KnowledgeChunk.objects.filter(document=document, embedding__isnull=True).exists()):
                raise ValueError('Document is incomplete')
            from django.db import connections
            with connections[DB].cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(hashlib.sha256(document.source_key.encode()).hexdigest()[:15], 16)])
            if KnowledgeDocument.objects.filter(source_key=document.source_key, status='published', version__gt=document.version).exists():
                raise ValueError('A newer version is already published')
            KnowledgeDocument.objects.filter(source_key=document.source_key, status='published').update(status='withdrawn')
            document.status = 'published'
            document.save(update_fields=['status', 'updated_at'])
            job.status, job.reviewed_by, job.reviewed_at = 'succeeded', actor_id, timezone.now()
        elif verb == 'withdraw':
            if document.status != 'published':
                raise ValueError('Only published documents can be withdrawn')
            document.status = 'withdrawn'
            document.save(update_fields=['status', 'updated_at'])
        else:
            raise ValueError('Unsupported import action')
        job.save()
        return job


def preview(job_id, actor_id, page=None, chunk=None, limit=20):
    operator(actor_id)
    job = KnowledgeImportJob.objects.select_related('document').get(pk=job_id)
    result = {'job_id': str(job.pk), 'document_id': str(job.document_id), 'status': job.status,
        'stage': job.stage, 'document_status': job.document.status, 'version': job.document.version,
        'total_pages': job.total_pages, 'processed_pages': job.processed_pages, 'attempt': job.attempt,
        'error_code': job.error_code, 'warnings': job.warnings,
        'chunk_count': KnowledgeChunk.objects.filter(document=job.document).count(),
        'embedded_chunks': KnowledgeChunk.objects.filter(document=job.document, embedding__isnull=False).count()}
    if page is not None:
        row = KnowledgePage.objects.get(document=job.document, number=page)
        result['page'] = {'number': row.number, 'status': row.status, 'method': row.method,
                          'blocks': row.blocks, 'warnings': row.warnings}
    if chunk is not None:
        result['chunks'] = list(KnowledgeChunk.objects.filter(document=job.document, ordinal__gte=chunk)
            .order_by('ordinal').values('ordinal', 'text', 'metadata')[:limit])
    return result


def preview_worker(job_id):
    return KnowledgeImportJob.objects.values('status', 'stage', 'processed_pages', 'total_pages', 'error_code').get(pk=job_id)
