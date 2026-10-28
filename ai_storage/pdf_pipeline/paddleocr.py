"""HTTP-only document adapter. No ORM, database tools or client-supplied URLs."""
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import time
from urllib.parse import urlsplit
import uuid

import requests

from ai_storage.vision.contracts import strict_json
from .page_ir import DocumentError, PAGE_IR_VERSION, normalize_native_page, normalize_page


CONTRACT_VERSION = 'paddle-document-v1'


@dataclass(frozen=True)
class DocumentConfig:
    base_url: str
    model: str
    revision: str
    timeout_seconds: int = 300
    max_image_bytes: int = 10000000
    max_output_tokens: int = 4096
    contract_version: str = CONTRACT_VERSION
    page_ir_version: str = PAGE_IR_VERSION

    def snapshot(self):
        return asdict(self)


def current_config():
    def env(name, default=''):
        return os.getenv('AI_PADDLEOCR_' + name, default).strip()
    try:
        config = DocumentConfig(base_url=env('BASE_URL').rstrip('/'),
            model=env('MODEL', 'PaddleOCR-VL-1.6-0.9B'), revision=env('REVISION'),
            timeout_seconds=int(env('TIMEOUT_SECONDS', '300')),
            max_image_bytes=int(env('MAX_IMAGE_BYTES', '10000000')),
            max_output_tokens=int(env('MAX_OUTPUT_TOKENS', '4096')))
        url = urlsplit(config.base_url)
        permitted = {'127.0.0.1', 'localhost', '::1'}
        permitted.update(h.strip() for h in env('ALLOW_HTTP_HOSTS').split(',') if h.strip())
        if (url.scheme not in ('http', 'https') or not url.hostname or url.username or url.password
                or url.query or url.fragment or url.path not in ('', '/')
                or (url.scheme == 'http' and url.hostname not in permitted)
                or (url.port is not None and not 1 <= url.port <= 65535)
                or any(c.isspace() for c in config.base_url)
                or not re.fullmatch(r'[0-9a-f]{64}', config.revision)
                or config.model != 'PaddleOCR-VL-1.6-0.9B'
                or not 1 <= config.timeout_seconds <= 900
                or not 1024 <= config.max_image_bytes <= 20000000
                or not 256 <= config.max_output_tokens <= 8192
                or len(env('API_KEY')) < 24):
            raise ValueError()
        return config
    except (ValueError, TypeError):
        raise DocumentError('DOCUMENT_INVALID_CONFIG') from None


def freeze(backend='legacy', mode='auto'):
    if backend not in ('legacy', 'paddleocr') or mode not in ('auto', 'force'):
        raise DocumentError('DOCUMENT_INVALID_MODE')
    if backend == 'legacy':
        return {'backend': 'legacy'}
    return {'backend': backend, 'mode': mode, 'config': current_config().snapshot()}


class PaddleOCRDocumentAdapter:
    def __init__(self, config, session=None):
        self.config = config
        self.session = session or requests.Session()
        self._owns_session = session is None
        # Explicit endpoint; private page uploads must not inherit desktop proxy settings.
        self.session.trust_env = False
        self.key = os.environ.get('AI_PADDLEOCR_API_KEY', '').strip()

    def close(self):
        if self._owns_session:
            self.session.close()

    def extract(self, image):
        import base64
        if (not isinstance(image, bytes) or not 24 <= len(image) <= self.config.max_image_bytes
                or not image.startswith(b'\x89PNG\r\n\x1a\n')):
            raise DocumentError('DOCUMENT_INVALID_IMAGE')
        deadline = time.monotonic() + self.config.timeout_seconds
        response = None
        try:
            response = self.session.post(self.config.base_url + '/layout-parsing',
                headers={'Authorization': 'Bearer ' + self.key},
                json={'file': base64.b64encode(image).decode('ascii'), 'fileType': 1,
                      'maxNewTokens': self.config.max_output_tokens,
                      'expectedRevision': self.config.revision},
                timeout=(5, self.config.timeout_seconds), stream=True, allow_redirects=False)
            if response.status_code != 200:
                code = {401: 'DOCUMENT_AUTH_FAILED', 403: 'DOCUMENT_AUTH_FAILED',
                        409: 'DOCUMENT_SERVICE_CHANGED', 429: 'DOCUMENT_BUSY',
                        503: 'DOCUMENT_UNAVAILABLE', 507: 'DOCUMENT_GPU_OOM'}.get(
                            response.status_code, 'DOCUMENT_HTTP_ERROR')
                raise DocumentError(code)
            parts, size = [], 0
            for chunk in response.iter_content(8192):
                size += len(chunk)
                if size > 4000000:
                    raise DocumentError('DOCUMENT_RESPONSE_TOO_LARGE')
                if time.monotonic() > deadline:
                    raise DocumentError('DOCUMENT_TIMEOUT')
                parts.append(chunk)
            body = strict_json(b''.join(parts).decode('utf8'))
            identity = body['identity']
            if (body['errorCode'] != 0 or identity.get('contract_version') != CONTRACT_VERSION
                    or identity.get('model') != self.config.model
                    or identity.get('revision') != self.config.revision):
                raise DocumentError('DOCUMENT_SERVICE_CHANGED')
            results = body['result']['layoutParsingResults']
            if not isinstance(results, list) or len(results) != 1:
                raise DocumentError('DOCUMENT_INVALID_RESPONSE')
            if not isinstance(body['warnings'], list) or any(
                    code != 'document_blocking_output_truncated' for code in body['warnings']):
                raise DocumentError('DOCUMENT_INVALID_RESPONSE')
            return {'raw': results[0]['prunedResult'], 'identity': identity, 'warnings': body['warnings']}
        except requests.Timeout:
            # No automatic replay: a timed-out request can still occupy the GPU server.
            raise DocumentError('DOCUMENT_TIMEOUT') from None
        except requests.RequestException:
            raise DocumentError('DOCUMENT_UNAVAILABLE') from None
        except DocumentError:
            raise
        except (ValueError, KeyError, TypeError, AttributeError, UnicodeError):
            raise DocumentError('DOCUMENT_INVALID_RESPONSE') from None
        finally:
            if response is not None:
                response.close()


class PaddlePageProcessor:
    def __init__(self, snapshot, *, cache_root, namespace):
        self.snapshot = snapshot
        self.config = current_config()
        if snapshot.get('config') != self.config.snapshot():
            raise DocumentError('DOCUMENT_CONFIG_CHANGED')
        self.adapter = PaddleOCRDocumentAdapter(self.config)
        self.cache_root = Path(cache_root)
        self.scope = hashlib.sha256(namespace.encode('utf8')).hexdigest()
        self.calls = self.hits = self.pages = 0

    def close(self):
        self.adapter.close()

    def process(self, original, image):
        if not original.get('has_content', bool(original['blocks'])):
            return normalize_native_page(original)
        risks = {'table_layout_requires_review', 'column_order_requires_review', 'low_ocr_confidence',
                 'sparse_or_broken_text', 'image_without_text', 'ocr_no_text'}
        needed = (self.snapshot['mode'] == 'force' or original['method'] != 'native'
                  or bool(risks.intersection(original['warnings'])))
        if not needed:
            return normalize_native_page(original)
        self.pages += 1
        iw, ih = struct.unpack('>II', image[16:24])
        geometry = original.get('render_geometry', {})
        if geometry.get('pixel_width') != iw or geometry.get('pixel_height') != ih:
            raise DocumentError('DOCUMENT_COORDINATE_MISMATCH')
        key = hashlib.sha256(json.dumps({'scope': self.scope, 'image': hashlib.sha256(image).hexdigest(),
            'page': original['number'], 'config': self.snapshot}, sort_keys=True).encode()).hexdigest()
        path = self.cache_root / self.scope / (key + '.json')
        try:
            if path.is_symlink():
                raise ValueError()
            if path.exists():
                if path.stat().st_size > 4000000:
                    raise ValueError()
                candidate = strict_json(path.read_text(encoding='utf8'))
                if candidate['key'] != key:
                    raise ValueError()
                result = candidate['result']
                self.hits += 1
            else:
                self.calls += 1
                result = self.adapter.extract(image)
            if (result['identity']['revision'] != self.config.revision
                    or result['identity']['model'] != self.config.model
                    or result['identity']['contract_version'] != CONTRACT_VERSION):
                raise ValueError()
            trace = dict(result['identity'], provider='paddleocr', input_sha256=hashlib.sha256(image).hexdigest(),
                         cache_digest=key, schema_version=PAGE_IR_VERSION)
            page = normalize_page(original, result['raw'], image_size=(iw, ih), identity=trace,
                                  warnings=result['warnings'])
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                temp = path.with_name(uuid.uuid4().hex + '.part')
                try:
                    with temp.open('x', encoding='utf8') as handle:
                        os.chmod(temp, 0o600)
                        json.dump({'key': key, 'result': result}, handle, allow_nan=False)
                    try:
                        os.link(temp, path)
                    except FileExistsError:
                        pass
                finally:
                    temp.unlink(missing_ok=True)
            return page
        except DocumentError:
            raise
        except (ValueError, KeyError, TypeError, OSError, struct.error):
            raise DocumentError('DOCUMENT_CACHE_OR_OUTPUT_INVALID') from None
