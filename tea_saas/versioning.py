"""Read deployed module versions from the same registry used for delivery."""
import json
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=None)
def module_version(name):
    registry = Path(__file__).resolve().parents[1] / 'versions/modules.json'
    return json.loads(registry.read_text(encoding='utf-8'))['modules'][name]['version']
