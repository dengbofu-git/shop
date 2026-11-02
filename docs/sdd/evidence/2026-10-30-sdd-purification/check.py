"""Read-only SDD checks; writes only this review's static-audit.json."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[4]
SDD = ROOT / 'docs/sdd'
HERE = Path(__file__).resolve().parent
errors = []


def require(condition, message):
    if not condition:
        errors.append(message)


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT).decode('utf-8').strip()


class UniqueLoader(yaml.SafeLoader):
    pass


def mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError('Duplicate YAML key: ' + str(key))
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, mapping)
active = sorted(p for p in SDD.rglob('*') if p.is_file() and
                'evidence' not in p.relative_to(SDD).parts)
documents = {}
link_count = 0
for path in active:
    content = path.read_text(encoding='utf-8-sig')
    if path.suffix in ('.yaml', '.yml'):
        documents[path.relative_to(ROOT).as_posix()] = yaml.load(content, Loader=UniqueLoader)
    if path.suffix == '.md':
        for target in re.findall(r'\]\(([^)]+)\)', content):
            if '://' in target or target.startswith('#'):
                continue
            target = target.split('#')[0]
            link_count += 1
            require((path.parent / target).exists(), f'Broken link: {path}: {target}')

catalog = documents['docs/sdd/catalog.yaml']
features = documents['docs/sdd/product/feature-inventory.yaml']['features']
versions = json.loads((ROOT / 'versions/modules.json').read_text(encoding='utf-8'))
modules = {x['id']: x for x in catalog['modules']}
caps = {x['id']: x for x in catalog['capabilities']}
require(len(modules) == len(catalog['modules']), 'Duplicate MOD ID')
require(len(caps) == len(catalog['capabilities']), 'Duplicate CAP ID')
require(len({x['id'] for x in features}) == len(features), 'Duplicate FEAT ID')
counts = dict(businessModules=len(modules), capabilities=len(caps),
              features=len(features), implementationModules=len(versions['modules']))
require(counts == catalog['currentAssessment']['counts'], 'Stale catalog counts')
for mid, module in modules.items():
    for cid in module['capabilityIds']:
        require(cid in caps and caps[cid]['moduleId'] == mid, f'MOD/CAP mismatch: {cid}')
for cid, cap in caps.items():
    require(cap['moduleId'] in modules and cid in modules[cap['moduleId']]['capabilityIds'],
            f'CAP/MOD mismatch: {cid}')
    for key in ('manifest', 'specification', 'productImportSpec'):
        if key in cap:
            require((ROOT / cap[key]).exists(), f'Missing {key}: {cid}')
for feature in features:
    cid = feature['primaryCapability']
    require(cid in caps and feature['id'] in caps[cid]['sourceFeatureIds'],
            f'FEAT primary mismatch: {feature["id"]}')
    for path in feature.get('codePaths', []):
        require((ROOT / path).exists(), f'Missing source path: {path}')
for cid, cap in caps.items():
    actual = {f['id'] for f in features if f['primaryCapability'] == cid}
    require(actual == set(cap['sourceFeatureIds']), f'CAP FEAT set mismatch: {cid}')
for name, doc in documents.items():
    if name.endswith('/capability.yaml'):
        parent = (ROOT / name).parent
        for path in doc.get('files', {}).values():
            require((parent / path).exists(), f'Missing capability file: {name}: {path}')
        require('gateAssessment' not in doc, f'Legacy stage gate: {name}')
        require(doc['assessment'] == caps[doc['id']]['assessment'], f'Assessment mismatch: {name}')
    if name.endswith('/open-questions.yaml'):
        require(all('blockingFrom' not in q for q in doc['questions']), 'Legacy blockingFrom')

changed = git('diff', '--name-only', 'HEAD').splitlines()
untracked = git('ls-files', '--others', '--exclude-standard').splitlines()
for path in changed + untracked:
    require(path.startswith('docs/sdd/'), f'Out-of-scope edit: {path}')
    if '/evidence/' in path:
        require(path.startswith(HERE.relative_to(ROOT).as_posix() + '/'),
                f'Old evidence changed: {path}')
require(not git('diff', '--cached', '--name-only'), 'Unexpected staged changes')
report = {
    'date': '2026-10-30', 'timezone': 'Asia/Shanghai', 'head': git('rev-parse', 'HEAD'),
    'branch': git('branch', '--show-current'), 'counts': counts,
    'activeDocumentCount': len(active), 'yamlCount': len(documents),
    'localMarkdownLinksChecked': link_count, 'errors': errors,
    'scope': 'static-documents-and-selected-source-only',
    'businessTests': 'not-run', 'databaseAndRuntime': 'not-checked',
    'existingEvidence': 'no tracked changes outside this review',
    'activeDocumentSha256': {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in active},
}
(HERE / 'static-audit.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps({k: v for k, v in report.items() if k != 'activeDocumentSha256'}, ensure_ascii=False))
raise SystemExit(bool(errors))
