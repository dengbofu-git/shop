import hashlib
import os
from pathlib import Path
import uuid

from django.conf import settings


def root():
    return Path(getattr(settings, 'AI_PDF_STORAGE_ROOT',
        os.getenv('AI_PDF_STORAGE_ROOT') or settings.BASE_DIR / '.scratch/knowledge-files')).resolve()


def job_path(job_id, name='source.pdf'):
    identity = str(uuid.UUID(str(job_id)))
    if name != 'source.pdf' and not (name.startswith('page-') and name[5:-4].isdigit() and name.endswith('.png')):
        raise ValueError('Invalid managed artifact')
    path = root() / identity / name
    if not path.resolve().is_relative_to(root()):
        raise ValueError('Invalid storage location')
    return path


def store_pdf(source, job_id, maximum):
    """Stream to an exclusive staging name; never trust a caller-supplied destination."""
    source = Path(source)
    if not source.is_file() or source.is_symlink():
        raise ValueError('PDF source must be a regular local file')
    dest = job_path(job_id)
    dest.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = dest.with_name(uuid.uuid4().hex + '.part')
    digest, size = hashlib.sha256(), 0
    try:
        with source.open('rb') as incoming, temporary.open('xb') as outgoing:
            os.chmod(str(temporary), 0o600)
            header = incoming.read(1024)
            if not header.startswith(b'%PDF-'):
                raise ValueError('Invalid PDF header')
            part = header
            while part:
                size += len(part)
                if size > maximum:
                    raise ValueError('PDF exceeds the configured byte limit')
                digest.update(part)
                outgoing.write(part)
                part = incoming.read(1024 * 1024)
        if size == 0:
            raise ValueError('Empty PDF')
        os.replace(str(temporary), str(dest))
        return digest.hexdigest()
    except Exception:
        temporary.unlink(missing_ok=True)
        if not dest.exists():
            dest.parent.rmdir()
        raise
    finally:
        temporary.unlink(missing_ok=True)


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for part in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(part)
    return digest.hexdigest()
