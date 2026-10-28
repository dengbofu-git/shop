"""Application-signed, short-lived stdio grants and a private per-request channel."""
import os
import time
from pathlib import Path

from django.core import signing

GRANT_ENV = 'TEA_SAAS_AGENT_GRANT'
AUDIENCE = 'tea-saas-agent-data-v1'
SALT = 'support-ai-mcp-grant-v1'
PRIVATE_SALT = 'support-ai-mcp-private-v1'
MAX_BYTES = 262144


class AccessDenied(RuntimeError):
    pass


def issue_grant(payload):
    return signing.dumps(dict(payload, audience=AUDIENCE), salt=SALT, compress=True)


def verify_grant(token, *, claim=True):
    try:
        payload = signing.loads(token, salt=SALT, max_age=150)
        if (payload['audience'] != AUDIENCE or time.time() > payload['expires_at']
                or payload['expires_at'] - payload['issued_at'] > 120
                or payload['issued_at'] > time.time() + 2
                or type(payload['owner_id']) not in (int, type(None))
                or (payload['owner_id'] is not None and payload['owner_id'] <= 0)):
            raise ValueError()
        folder = Path(payload['private_dir'])
        if not folder.is_absolute() or not folder.is_dir() or folder.is_symlink():
            raise ValueError()
        if claim:
            # One backend owns the entire grant: no resetting its counters by
            # starting another process with the same token.
            descriptor = os.open(str(folder / 'claimed'), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            os.close(descriptor)
        return payload
    except (signing.BadSignature, ValueError, TypeError, KeyError, OSError):
        raise AccessDenied('Invalid MCP access context') from None


def write_private(folder, name, payload):
    target = Path(folder) / name
    encoded = signing.dumps(payload, salt=PRIVATE_SALT).encode('utf-8')
    if len(encoded) > MAX_BYTES:
        raise AccessDenied('Private message limit')
    temporary = target.with_suffix('.pending')
    descriptor = os.open(str(temporary), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, 'wb') as stream:
        stream.write(encoded)
    os.replace(str(temporary), str(target))


def read_private(folder, name, nonce, sequence):
    try:
        with (Path(folder) / name).open('rb') as stream:
            raw = stream.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise ValueError()
        result = signing.loads(raw.decode('utf-8'), salt=PRIVATE_SALT, max_age=150)
        if result['nonce'] != nonce or result['sequence'] != sequence:
            raise ValueError()
        return result
    except (OSError, ValueError, KeyError, TypeError, signing.BadSignature):
        raise AccessDenied('Invalid MCP private handoff') from None
