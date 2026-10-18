#!/usr/bin/env python3
"""Independent module versions for the 跨境茶叶saas平台 monorepo (stdlib only)."""
import argparse
import datetime
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / 'versions' / 'modules.json'
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def git(*args):
    return subprocess.check_output(
        ['git', '-c', 'safe.directory=' + ROOT.as_posix(), *args],
        cwd=ROOT, stderr=subprocess.PIPE,
    ).decode('utf-8')


def read_registry():
    data = json.loads(REGISTRY.read_text(encoding='utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('Unsupported registry schema')
    modules = data['modules']
    used_paths = set()
    for name, module in modules.items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', name):
            raise ValueError('Invalid module name: ' + name)
        if not SEMVER.fullmatch(module['version']):
            raise ValueError('Invalid version: ' + name)
        for path in module['paths']:
            if path.startswith('/') or '..' in Path(path).parts or '\\' in path:
                raise ValueError('Invalid module path: ' + path)
            if path in used_paths:
                raise ValueError('Duplicate module path: ' + path)
            used_paths.add(path)
        if set(module['dependencies']) - set(modules):
            raise ValueError('Unknown dependency: ' + name)
        if not (ROOT / 'versions' / 'changelogs' / (name + '.md')).is_file():
            raise ValueError('Missing changelog: ' + name)
    return data


def owner(path, modules):
    matches = [(len(prefix), name) for name, module in modules.items()
               for prefix in module['paths']
               if path == prefix or path.startswith(prefix.rstrip('/') + '/')]
    return max(matches)[1] if matches else None


def changed_paths(base):
    # Includes committed changes, staged/unstaged changes and untracked files.
    paths = set()
    if base:
        paths.update(git('diff', '--name-only', '-z', base, 'HEAD').split('\0'))
    paths.update(git('diff', '--name-only', '-z', 'HEAD').split('\0'))
    paths.update(git('ls-files', '--others', '--exclude-standard', '-z').split('\0'))
    return sorted(path for path in paths if path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('list', help='List module versions')
    commands.add_parser('check', help='Validate registry and tracked-file ownership')
    changed = commands.add_parser('changed', help='Find changed modules and dependent modules')
    changed.add_argument('--base', help='Compare against a Git ref, plus working tree changes')
    bump = commands.add_parser('bump', help='Update one version and its changelog; does not commit')
    bump.add_argument('module')
    bump.add_argument('level', choices=['patch', 'minor', 'major'])
    bump.add_argument('--note', required=True, help='Release description')
    tag = commands.add_parser('tag', help='Create a local annotated release tag; does not push')
    tag.add_argument('module', help='Module name or all')
    args = parser.parse_args()
    data = read_registry()
    modules = data['modules']

    if args.command == 'list':
        for name, module in modules.items():
            print('{}\t{}\t{}'.format(name, module['version'], module['title']))
    elif args.command == 'check':
        unowned = [path for path in git('ls-files', '-z').split('\0')
                   if path and not owner(path, modules)]
        if unowned:
            raise ValueError('Files without a module:\n' + '\n'.join(unowned))
        print('OK: {} modules; all tracked files have an owner'.format(len(modules)))
    elif args.command == 'changed':
        groups = {}
        for path in changed_paths(args.base):
            if path == 'versions/modules.json':
                # Version-only edits belong to their modules, not to core.
                try:
                    old = json.loads(git('show', (args.base or 'HEAD') + ':versions/modules.json'))
                except subprocess.CalledProcessError:
                    old = None
                if old is not None:
                    old_modules = old.get('modules', {})
                    for name in set(old_modules) | set(modules):
                        if old_modules.get(name) != modules.get(name):
                            groups.setdefault(name, []).append(path)
                    continue
            groups.setdefault(owner(path, modules) or 'UNASSIGNED', []).append(path)
        for name, paths in sorted(groups.items()):
            print(name + ':')
            for path in paths:
                print('  ' + path)
        affected = set(groups) & set(modules)
        dependents = set()
        while True:
            added = {name for name, module in modules.items()
                     if set(module['dependencies']) & (affected | dependents)} - affected - dependents
            if not added:
                break
            dependents.update(added)
        if dependents:
            print('Review compatibility for: ' + ', '.join(sorted(dependents)))
        if not groups:
            print('No changes')
    elif args.command == 'bump':
        if args.module not in modules:
            raise ValueError('Unknown module: ' + args.module)
        note = args.note.strip()
        if not note or '\n' in note or '\r' in note:
            raise ValueError('Provide a nonempty, single-line release note')
        module = modules[args.module]
        parts = list(map(int, module['version'].split('.')))
        index = {'major': 0, 'minor': 1, 'patch': 2}[args.level]
        parts[index] += 1
        for i in range(index + 1, 3):
            parts[i] = 0
        version = '.'.join(map(str, parts))
        tag_name = '{}/v{}'.format(args.module, version)
        if git('tag', '--list', tag_name).strip():
            raise ValueError('Release tag already exists: ' + tag_name)
        changelog = ROOT / 'versions' / 'changelogs' / (args.module + '.md')
        text = changelog.read_text(encoding='utf-8')
        heading, separator, rest = text.partition('\n')
        date = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).date()
        entry = '\n## {} - {}\n\n- {}\n'.format(version, date, note)
        module['version'] = version
        REGISTRY.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        changelog.write_text(heading + '\n' + entry + rest, encoding='utf-8')
        print('{} -> {}. Commit registry, changelog and module changes together.'.format(args.module, version))
    elif args.command == 'tag':
        if git('status', '--porcelain').strip():
            raise ValueError('Commit or stash working tree changes before tagging')
        committed = json.loads(git('show', 'HEAD:versions/modules.json'))
        if committed != data:
            raise ValueError('Registry must match HEAD')
        selected = list(modules) if args.module == 'all' else [args.module]
        tags = []
        for name in selected:
            if name not in modules:
                raise ValueError('Unknown module: ' + name)
            tag_name = '{}/v{}'.format(name, modules[name]['version'])
            if git('tag', '--list', tag_name).strip():
                raise ValueError('Tag already exists: ' + tag_name)
            tags.append((name, tag_name))
        for name, tag_name in tags:
            git('tag', '-a', tag_name, '-m', '{} {}'.format(modules[name]['title'], modules[name]['version']))
            print(tag_name)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as exc:
        if isinstance(exc, subprocess.CalledProcessError):
            print(exc.stderr.decode('utf-8', errors='replace'), file=sys.stderr)
        else:
            print(str(exc), file=sys.stderr)
        sys.exit(1)
