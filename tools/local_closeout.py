"""Snapshot-bound local promotion; never reset, stash, force-remove or publish."""
import hashlib
import json
from pathlib import Path
import re
import os
import sys
import subprocess
import zipfile


class UnsafeCloseout(RuntimeError):
    pass


def git(root, *args):
    result = subprocess.run(['git', *args], cwd=root, capture_output=True)
    if result.returncode:
        raise UnsafeCloseout(result.stderr.decode('utf-8', 'replace').strip())
    return result.stdout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def safe_root(value):
    path = Path(value).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise UnsafeCloseout('Linked source/destination is not supported')
    if not path.is_dir() or not (path / '.git').exists():
        raise UnsafeCloseout('Expected an existing Git workspace')
    return path.resolve()


def safe_file(root, relative):
    path = root / relative
    if Path(relative).is_absolute() or '..' in Path(relative).parts or path.resolve().is_relative_to(root) is False:
        raise UnsafeCloseout('Path escapes workspace')
    for parent in (path, *path.parents):
        if parent == root:
            break
        if parent.is_symlink() or (hasattr(parent, 'is_junction') and parent.is_junction()):
            raise UnsafeCloseout('Linked file is not supported')
    return path


def names(root, *args):
    return sorted(set(x for x in git(root, *args, '-z').decode('utf-8').split('\0') if x))


def snapshot(root):
    files = {}
    for relative in names(root, 'ls-files', '--cached', '--others', '--exclude-standard'):
        path = safe_file(root, relative)
        if path.is_file():
            files[relative] = digest(path.read_bytes())
    return {'head': git(root, 'rev-parse', 'HEAD').decode().strip(),
            'status': git(root, 'status', '--porcelain=v1', '-z', '--untracked-files=all').decode(),
            'index': digest(git(root, 'diff', '--cached', '--binary')), 'files': files}


def create_plan(destination, source, recovery, branch, base='origin/main'):
    destination, source = safe_root(destination), safe_root(source)
    recovery = Path(recovery).resolve()
    if destination == source or recovery.is_relative_to(source):
        raise UnsafeCloseout('Recovery must outlive the source workspace')
    if not branch.startswith('codex/'):
        raise UnsafeCloseout('A new development branch is required')
    primary = snapshot(destination)
    if primary['index'] != digest(b''):
        raise UnsafeCloseout('Staged intent must be reconciled separately')
    current = snapshot(source)
    main = git(destination, 'rev-parse', base).decode().strip()
    if current['head'] != main:
        raise UnsafeCloseout('Integrated source must start at the reviewed main SHA')
    migration_paths = [p for p in names(source, 'ls-tree', '-r', '--name-only', main)
                       if re.search(r'(^|/)migrations/\d+_[^/]+\.py$', p)]
    local_migrations = [p for p in current['files'] if re.search(r'(^|/)migrations/\d+_[^/]+\.py$', p)]
    if set(migration_paths) != set(local_migrations):
        raise UnsafeCloseout('Migration inventory differs from reviewed main')
    for relative in migration_paths:
        if safe_file(source, relative).read_bytes().replace(b'\r\n', b'\n') != git(source, 'show', main + ':' + relative).replace(b'\r\n', b'\n'):
            raise UnsafeCloseout('Historical migration changed')
    # Fail before any write when the new branch already exists.
    refs = git(destination, 'for-each-ref', '--format=%(refname)', 'refs/heads').decode().splitlines()
    if 'refs/heads/' + branch in refs:
        raise UnsafeCloseout('Target branch already exists')
    recovery.mkdir(parents=True, exist_ok=True)
    archive = recovery / 'primary-before.zip'
    if archive.exists():
        raise UnsafeCloseout('Recovery material already exists; choose a fresh plan directory')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for relative in primary['files']:
            z.writestr(relative, safe_file(destination, relative).read_bytes())
    verify_archive(archive, primary['files'])
    plan = {'schema': 1, 'destination': str(destination), 'source': str(source),
            'recovery': str(recovery), 'branch': branch, 'base': base, 'main': main,
            'primary': primary, 'integrated': current, 'archive_sha': digest(archive.read_bytes())}
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode('utf-8')
    (recovery / 'plan.json').write_bytes(raw)
    return plan, digest(raw)


def verify_archive(archive, files):
    with zipfile.ZipFile(archive) as z:
        if set(z.namelist()) != set(files) or z.testzip() is not None:
            raise UnsafeCloseout('Incomplete recovery archive')
        if any(digest(z.read(name)) != value for name, value in files.items()):
            raise UnsafeCloseout('Recovery hash mismatch')


def apply_plan(plan_path, expected_hash):
    plan_path = Path(plan_path)
    raw = plan_path.read_bytes()
    if digest(raw) != expected_hash:
        raise UnsafeCloseout('Plan hash mismatch')
    plan = json.loads(raw)
    destination, source = safe_root(plan['destination']), safe_root(plan['source'])
    recovery = Path(plan['recovery']).resolve()
    journal = recovery / 'journal.json'
    if journal.exists():
        raise UnsafeCloseout('An attempted plan must be recovered/reviewed, never replayed')
    if git(destination, 'rev-parse', plan['base']).decode().strip() != plan['main']:
        raise UnsafeCloseout('Main changed after review')
    if snapshot(destination) != plan['primary'] or snapshot(source) != plan['integrated']:
        raise UnsafeCloseout('Workspace changed after review')
    archive = recovery / 'primary-before.zip'
    if digest(archive.read_bytes()) != plan['archive_sha']:
        raise UnsafeCloseout('Recovery archive changed')
    verify_archive(archive, plan['primary']['files'])
    # Persistent evidence exists before the first mutation.
    events = []
    def record(step, state):
        events.append({'step': step, 'state': state})
        journal.write_text(json.dumps(events, indent=2), encoding='utf-8')
    tracked_changes = names(destination, 'diff', '--name-only', '--no-renames', 'HEAD')
    untracked = names(destination, 'ls-files', '--others', '--exclude-standard')
    # Asset directories and real environment files are never reconciled as source.
    protected = ('.env', '.env.postgres', 'media/', 'app_key/')
    if any(p in protected or p.startswith(('media/', 'app_key/')) for p in tracked_changes):
        raise UnsafeCloseout('Modified runtime assets require an explicit separate plan')
    record('restore-reviewed-primary-source', 'started')
    # Historical blobs contain mixed EOLs. Preserve their bytes for this
    # transition instead of applying the user's shared autocrlf conversion.
    tracked = [p for p in names(destination, 'ls-files', '--cached')
               if p not in protected and not p.startswith(('media/', 'app_key/'))]
    pathspec = recovery / 'reviewed-tracked-paths.nul'
    pathspec.write_bytes(b'\0'.join(p.encode('utf-8') for p in tracked) + b'\0')
    git(destination, '-c', 'core.autocrlf=false', 'restore', '--source=HEAD', '--worktree',
        '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul')
    record('restore-reviewed-primary-source', 'complete')
    record('remove-backed-up-untracked-source', 'started')
    for relative in untracked:
        if relative in protected or relative.startswith(('media/', 'app_key/')):
            continue
        path = safe_file(destination, relative)
        if not path.is_file() or digest(path.read_bytes()) != plan['primary']['files'].get(relative):
            raise UnsafeCloseout('Untracked source changed during apply')
        path.unlink()
    record('remove-backed-up-untracked-source', 'complete')
    head_files = {}
    for item in git(destination, 'ls-tree', '-r', '-z', 'HEAD').split(b'\0'):
        if item:
            meta, relative = item.split(b'\t', 1)
            head_files[relative.decode('utf-8')] = meta.split()[2].decode()
    for relative in tracked:
        data = safe_file(destination, relative).read_bytes()
        object_id = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
        if object_id != head_files[relative]:
            expected = git(destination, 'show', 'HEAD:' + relative)
            if data.replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
                raise UnsafeCloseout('Restored source differs from original HEAD')
            # Git may leave an already-clean CRLF file untouched even when
            # restore is called with autocrlf=false. Materialize only the
            # already-verified original bytes, preserving the backup above.
            safe_file(destination, relative).write_bytes(expected)
    if digest(git(destination, 'diff', '--cached', '--binary')) != plan['primary']['index']:
        raise UnsafeCloseout('Staged intent changed before checkout')
    record('checkout-new-main-development-branch', 'started')
    # Normal preserving merge handles stale Windows stat flags. The preceding
    # object-ID check proves there are no content edits to silently discard.
    git(destination, '-c', 'core.autocrlf=false', 'switch', '--merge', '-c', plan['branch'], plan['main'])
    if git(destination, 'ls-files', '--unmerged'):
        raise UnsafeCloseout('Unexpected checkout conflict; manual review required')
    record('checkout-new-main-development-branch', 'complete')
    record('copy-reviewed-integrated-source', 'started')
    for relative, checksum in plan['integrated']['files'].items():
        incoming = safe_file(source, relative)
        data = incoming.read_bytes()
        if digest(data) != checksum:
            raise UnsafeCloseout('Integrated source changed during apply')
        outgoing = safe_file(destination, relative)
        if outgoing.is_file() and outgoing.read_bytes().replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n'):
            continue
        if relative in protected or relative.startswith(('media/', 'app_key/')):
            raise UnsafeCloseout('Integrated runtime asset differs')
        previous = subprocess.run(['git', 'show', plan['main'] + ':' + relative], cwd=destination, capture_output=True)
        if outgoing.exists():
            if previous.returncode or outgoing.read_bytes().replace(b'\r\n', b'\n') != previous.stdout.replace(b'\r\n', b'\n'):
                raise UnsafeCloseout('Destination received a new edit during promotion')
        elif previous.returncode == 0:
            raise UnsafeCloseout('Destination file disappeared during promotion')
        outgoing.parent.mkdir(parents=True, exist_ok=True)
        outgoing.write_bytes(data)
    record('copy-reviewed-integrated-source', 'complete')
    return snapshot(destination)


def recover_before_switch(plan_path, expected_hash):
    """Restore an interrupted pre-checkout state only when every byte is known."""
    raw = Path(plan_path).read_bytes()
    if digest(raw) != expected_hash:
        raise UnsafeCloseout('Plan hash mismatch')
    plan = json.loads(raw)
    destination = safe_root(plan['destination'])
    recovery = Path(plan['recovery'])
    journal = recovery / 'journal.json'
    events = json.loads(journal.read_text(encoding='utf-8'))
    if events[-1] != {'step': 'checkout-new-main-development-branch', 'state': 'started'}:
        raise UnsafeCloseout('This interrupted stage requires separate recovery review')
    if git(destination, 'rev-parse', 'HEAD').decode().strip() != plan['primary']['head']:
        raise UnsafeCloseout('HEAD advanced; refusing recovery')
    if digest(git(destination, 'diff', '--cached', '--binary')) != plan['primary']['index']:
        raise UnsafeCloseout('Staged intent changed; refusing recovery')
    archive = recovery / 'primary-before.zip'
    if digest(archive.read_bytes()) != plan['archive_sha']:
        raise UnsafeCloseout('Recovery archive changed')
    verify_archive(archive, plan['primary']['files'])
    current = snapshot(destination)['files']
    for relative, checksum in current.items():
        if relative not in plan['primary']['files']:
            raise UnsafeCloseout('New source appeared during interruption')
        if checksum == plan['primary']['files'][relative]:
            continue
        previous = git(destination, 'show', plan['primary']['head'] + ':' + relative)
        if safe_file(destination, relative).read_bytes().replace(b'\r\n', b'\n') != previous.replace(b'\r\n', b'\n'):
            raise UnsafeCloseout('New edit appeared during interruption')
    with zipfile.ZipFile(archive) as z:
        for relative in plan['primary']['files']:
            outgoing = safe_file(destination, relative)
            if outgoing.is_file() and digest(outgoing.read_bytes()) == plan['primary']['files'][relative]:
                continue
            outgoing.parent.mkdir(parents=True, exist_ok=True)
            outgoing.write_bytes(z.read(relative))
    if snapshot(destination)['files'] != plan['primary']['files']:
        raise UnsafeCloseout('Recovery verification failed')
    events.append({'step': 'recover-primary-before-checkout', 'state': 'complete'})
    journal.write_text(json.dumps(events, indent=2), encoding='utf-8')


def in_use(workspace):
    """Fail closed when Windows service inspection is unavailable."""
    if os.name != 'nt':
        raise UnsafeCloseout('This retirement process audit currently supports Windows only')
    script = r'''Get-CimInstance Win32_Process | Where-Object {
        $_.Name -match 'python|node' -and $_.CommandLine -match 'manage\.py|runtime[\\/]backend\.py|tea_saas_mcp\.resident|support_stream_browser'
    } | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress'''
    result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], capture_output=True)
    if result.returncode:
        raise UnsafeCloseout('Could not inspect application processes')
    needle = str(workspace).replace('\\', '/').lower()
    if needle in result.stdout.decode('utf-8', 'replace').replace('\\\\', '/').replace('\\', '/').lower():
        return True
    mounts = subprocess.run(['docker', 'inspect', '--format', '{{json .Mounts}}',
        'tea_saas-knowledge-worker-knowledge-worker-1'], capture_output=True)
    if mounts.returncode:
        raise UnsafeCloseout('Could not inspect the knowledge worker mount')
    for mount in json.loads(mounts.stdout):
        if mount['Destination'] == '/app' and Path(mount['Source']).resolve().is_relative_to(workspace):
            return True
    return False


def head_blobs(root):
    paths = names(root, 'ls-files', '--cached')
    if any('\n' in p or '\r' in p for p in paths):
        raise UnsafeCloseout('Unsupported Git filename')
    result = subprocess.run(['git', 'cat-file', '--batch'], cwd=root,
        input=b''.join(('HEAD:' + p + '\n').encode('utf-8') for p in paths), capture_output=True)
    if result.returncode:
        raise UnsafeCloseout('Could not read original Git blobs')
    data, offset, blobs = result.stdout, 0, {}
    for path in paths:
        end = data.index(b'\n', offset)
        header = data[offset:end].split()
        if len(header) != 3 or header[1] != b'blob':
            raise UnsafeCloseout('Submodules or unsupported objects require separate review')
        size = int(header[2]); offset = end + 1
        blobs[path] = data[offset:offset + size]; offset += size + 1
    return blobs


def create_retirement_plan(canonical, workspace, recovery, base='origin/main'):
    canonical, workspace = safe_root(canonical), safe_root(workspace)
    recovery = Path(recovery).resolve()
    if canonical == workspace or not (workspace / '.git').is_file() or recovery.is_relative_to(workspace):
        raise UnsafeCloseout('Primary/shared workspace or in-tree recovery cannot be retired')
    common = git(canonical, 'rev-parse', '--git-common-dir').decode().strip()
    common = (canonical / common).resolve()
    other_common = git(workspace, 'rev-parse', '--git-common-dir').decode().strip()
    if (workspace / other_common).resolve() != common:
        raise UnsafeCloseout('Workspace belongs to another repository')
    state = snapshot(workspace)
    if state['index'] != digest(b''):
        raise UnsafeCloseout('Staged intent must be retained and reviewed separately')
    main = git(canonical, 'rev-parse', base).decode().strip()
    git(canonical, 'merge-base', '--is-ancestor', state['head'], main)
    recovery.mkdir(parents=True, exist_ok=True)
    archive = recovery / 'workspace-before.zip'
    if archive.exists():
        raise UnsafeCloseout('A fresh retirement plan directory is required')
    # Keep needed ignored assets; installed dependencies and bytecode are
    # reproducible, and runtime use is independently rejected during apply.
    files = dict(state['files'])
    skip = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
    for parent, dirs, filenames in os.walk(workspace, followlinks=False):
        dirs[:] = [d for d in dirs if d not in skip]
        for name in filenames:
            path = Path(parent) / name
            relative = path.relative_to(workspace).as_posix()
            if relative == '.git':
                continue
            path = safe_file(workspace, relative)
            if path.is_file():
                files[relative] = digest(path.read_bytes())
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED) as z:
        for relative in files:
            z.writestr(relative, safe_file(workspace, relative).read_bytes())
    verify_archive(archive, files)
    plan = {'canonical': str(canonical), 'workspace': str(workspace), 'base': base, 'main': main,
            'state': state, 'assets': files, 'recovery': str(recovery), 'archive_sha': digest(archive.read_bytes())}
    raw = json.dumps(plan, ensure_ascii=False, sort_keys=True).encode('utf-8')
    (recovery / 'retirement.json').write_bytes(raw)
    return digest(raw)


def reject_embedded_repositories(workspace):
    skip = {'.git', '.venv', 'venv', 'node_modules', '__pycache__', '.pytest_cache'}
    for parent, dirs, files in os.walk(workspace, followlinks=False):
        if Path(parent) != workspace and ('.git' in dirs or '.git' in files):
            raise UnsafeCloseout('Embedded repository requires its own recovery plan')
        dirs[:] = [name for name in dirs if name not in skip]


def retire_workspace(plan_path, expected_hash):
    raw = Path(plan_path).read_bytes()
    if digest(raw) != expected_hash:
        raise UnsafeCloseout('Retirement plan changed')
    plan = json.loads(raw)
    canonical, workspace = safe_root(plan['canonical']), safe_root(plan['workspace'])
    recovery = Path(plan['recovery'])
    journal = recovery / 'retirement-result.json'
    if journal.exists() or canonical == workspace or not (workspace / '.git').is_file():
        raise UnsafeCloseout('Retirement was attempted or target identity changed')
    if git(canonical, 'rev-parse', plan['base']).decode().strip() != plan['main'] or snapshot(workspace) != plan['state']:
        raise UnsafeCloseout('Main/workspace changed after retirement review')
    if in_use(workspace):
        raise UnsafeCloseout('Workspace is still used by a service')
    reject_embedded_repositories(workspace)
    archive = recovery / 'workspace-before.zip'
    if digest(archive.read_bytes()) != plan['archive_sha']:
        raise UnsafeCloseout('Retirement recovery archive changed')
    verify_archive(archive, plan['assets'])
    for relative, checksum in plan['assets'].items():
        if digest(safe_file(workspace, relative).read_bytes()) != checksum:
            raise UnsafeCloseout('Ignored asset changed after review')
    # Clean workspaces use normal Git removal directly. Dirty, reviewed copies
    # are first materialized as their exact old HEAD and normally merged to the
    # reviewed main; all previous source and assets remain in the verified ZIP.
    journal.write_text(json.dumps({'state': 'started', 'workspace': str(workspace)}), encoding='utf-8')
    if plan['state']['status']:
        for relative, data in head_blobs(workspace).items():
            target = safe_file(workspace, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        for relative in names(workspace, 'ls-files', '--others', '--exclude-standard'):
            target = safe_file(workspace, relative)
            if target.is_file():
                if digest(target.read_bytes()) != plan['assets'].get(relative):
                    raise UnsafeCloseout('Untracked source changed during retirement')
                target.unlink()
        git(workspace, '-c', 'core.autocrlf=false', 'switch', '--merge', '--detach', plan['main'])
        if git(workspace, 'ls-files', '--unmerged'):
            raise UnsafeCloseout('Retirement encountered a conflict; no forced removal')
    if in_use(workspace):
        raise UnsafeCloseout('A service attached during retirement')
    # Windows can retain dirty stat flags after a content-identical restore.
    # Refresh exact, reviewed HEAD objects only; any actual staged delta blocks
    # removal instead of being discarded.
    for relative, expected in head_blobs(workspace).items():
        target = safe_file(workspace, relative)
        data = target.read_bytes()
        if data != expected:
            if data.replace(b'\r\n', b'\n') != expected.replace(b'\r\n', b'\n'):
                raise UnsafeCloseout('A new edit appeared before removal')
            target.write_bytes(expected)
    pathspec = recovery / 'clean-head-paths.nul'
    pathspec.write_bytes(b'\0'.join(p.encode('utf-8') for p in names(workspace, 'ls-files', '--cached')) + b'\0')
    git(workspace, '-c', 'core.autocrlf=false', 'add', '--update',
        '--pathspec-from-file=' + str(pathspec), '--pathspec-file-nul')
    if git(workspace, 'diff', '--cached', '--binary'):
        raise UnsafeCloseout('Index contains an actual change; no removal performed')
    git(canonical, 'worktree', 'remove', str(workspace))
    if workspace.exists():
        raise UnsafeCloseout('Git did not remove the workspace')
    journal.write_text(json.dumps({'state': 'recycled', 'workspace': str(workspace),
                                  'archive_sha': plan['archive_sha']}), encoding='utf-8')


def main():
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    audit = commands.add_parser('audit')
    audit.add_argument('root')
    plan = commands.add_parser('plan')
    for name in ('destination', 'source', 'recovery', 'branch'):
        plan.add_argument('--' + name, required=True)
    plan.add_argument('--base', default='origin/main')
    apply = commands.add_parser('apply')
    apply.add_argument('--plan', required=True)
    apply.add_argument('--sha256', required=True)
    recover = commands.add_parser('recover-before-switch')
    recover.add_argument('--plan', required=True)
    recover.add_argument('--sha256', required=True)
    args = parser.parse_args()
    if args.command == 'audit':
        result = snapshot(safe_root(args.root))
        print(json.dumps({'head': result['head'], 'files': len(result['files']), 'dirty': bool(result['status'])}))
    elif args.command == 'plan':
        _, sha = create_plan(args.destination, args.source, args.recovery, args.branch, args.base)
        print(json.dumps({'plan': str(Path(args.recovery) / 'plan.json'), 'sha256': sha}))
    elif args.command == 'apply':
        result = apply_plan(args.plan, args.sha256)
        print(json.dumps({'head': result['head'], 'files': len(result['files']), 'status': 'promoted'}))
    else:
        recover_before_switch(args.plan, args.sha256)
        print(json.dumps({'status': 'original-source-recovered'}))


if __name__ == '__main__':
    main()
