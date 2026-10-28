"""成功结果的私有内容缓存；不缓存失败或跨授权域复用结果。"""
import hashlib
import json
import os
from pathlib import Path
import uuid

from .contracts import VisionError, strict_json, validate_payload


class VisionCache:
    def __init__(self, root, namespace, config):
        self.root = Path(root).resolve()
        self.scope = hashlib.sha256(namespace.encode('utf8')).hexdigest()
        self.config = config

    def identity(self, image, task, context):
        identity = {'schema': 'vision-cache-v1', 'scope': self.scope, 'task': task,
                    'context': context, 'image_sha256': hashlib.sha256(image).hexdigest(),
                    'config': self.config.snapshot()}
        return hashlib.sha256(json.dumps(identity, sort_keys=True).encode('utf8')).hexdigest()

    def path(self, digest):
        if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
            raise VisionError('VISION_INVALID_CACHE_KEY')
        path = self.root / self.scope / digest[:2] / (digest + '.json')
        if not path.resolve().is_relative_to(self.root) or path.is_symlink():
            raise VisionError('VISION_INVALID_CACHE_PATH')
        return path

    def get(self, digest, task):
        path = self.path(digest)
        if not path.exists():
            return None
        try:
            if path.stat().st_size > 600000:
                raise ValueError()
            value = strict_json(path.read_text(encoding='utf8'))
            if (value['digest'] != digest or value['result']['task'] != task
                    or value['result']['model'] != self.config.model
                    or value['result']['revision'] != self.config.revision):
                raise ValueError()
            value['result']['payload'] = validate_payload(task, value['result']['payload'])
            return value['result']
        except (ValueError, KeyError, TypeError, OSError):
            raise VisionError('VISION_CACHE_INVALID') from None

    def put(self, digest, result):
        validate_payload(result['task'], result['payload'])
        path = self.path(digest)
        for folder in (self.root, self.root / self.scope, path.parent):
            folder.mkdir(parents=True, exist_ok=True, mode=0o700)
        temporary = path.with_name(uuid.uuid4().hex + '.part')
        try:
            with temporary.open('x', encoding='utf8') as handle:
                os.chmod(temporary, 0o600)
                json.dump({'digest': digest, 'result': result}, handle, ensure_ascii=False, allow_nan=False)
            # 同文件系统原子保留首个成功结果；并发输家读取胜出结果。
            try:
                os.link(temporary, path)
            except FileExistsError:
                pass
            return self.get(digest, result['task'])
        finally:
            temporary.unlink(missing_ok=True)
