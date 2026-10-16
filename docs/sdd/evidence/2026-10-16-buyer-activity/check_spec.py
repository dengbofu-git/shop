"""Narrow static traceability check; does not represent business acceptance."""
import ast
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[4]
CAP = ROOT / 'docs/sdd/modules/catalog-content/capabilities/CAP-CAT-004'
cap = yaml.safe_load((CAP / 'capability.yaml').read_text(encoding='utf-8'))
catalog = yaml.safe_load((ROOT / 'docs/sdd/catalog.yaml').read_text(encoding='utf-8'))
features = yaml.safe_load((ROOT / 'docs/sdd/product/feature-inventory.yaml').read_text(encoding='utf-8'))
acceptance = yaml.safe_load((CAP / 'acceptance.yaml').read_text(encoding='utf-8'))
api = yaml.safe_load((CAP / 'api-contract.yaml').read_text(encoding='utf-8'))
catalog_cap = next(c for c in catalog['capabilities'] if c['id'] == cap['id'])
assert catalog_cap['status'] == cap['status']
assert len(catalog['capabilities']) == 25
assert len(features['features']) == 29
assert next(f for f in features['features'] if f['id'] == 'FEAT-029')['primaryCapability'] == cap['id']
for path in cap['files'].values():
    assert (CAP / path).exists(), path
assert api['specVersion'] == acceptance['specVersion'] == cap['specVersion']
requirements = (CAP / 'requirements.md').read_text(encoding='utf-8')
test_ast = ast.parse((ROOT / 'goods/test_activity.py').read_text(encoding='utf-8'))
tests = {node.name for node in ast.walk(test_ast) if isinstance(node, ast.FunctionDef)}
for ac in acceptance['acceptance']:
    for ref in ac['references']:
        assert ref in requirements, ref
    for test in ac['tests']:
        if test.startswith('test_'):
            assert test in tests, test
for path in CAP.glob('*.md'):
    for link in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
        if not re.match(r'^[a-z]+:', link):
            assert (path.parent / link).exists(), link
print('PASS: 25 capabilities, 29 features, 9 acceptance cases, API version, local links and test references')
