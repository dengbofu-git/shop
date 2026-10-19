#!/usr/bin/env python3
"""tea_saas Git checks. Uses only the Python standard library and Git."""
import argparse
import ast
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BRANCH = re.compile(r'^(codex/[a-z0-9][a-z0-9._/-]*|owner/dengbofu)$')
TITLE = re.compile(r'^(feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)(\([a-z0-9_./-]+\))?!?: .+$')
MIGRATION = re.compile(r'^([^/]+)/migrations/(\d+)_[^/]+\.py$')
SEMVER = re.compile(r'^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$')


def git(*args, data=None):
    return subprocess.check_output(
        ['git', '-c', 'safe.directory=' + ROOT.as_posix(), *args], cwd=ROOT,
        input=data, stderr=subprocess.PIPE)


def output(*args):
    return git(*args).decode('utf-8').strip()


def require_branch(name=None):
    name = name if name is not None else output('branch', '--show-current')
    if not BRANCH.fullmatch(name):
        raise ValueError('开发分支须为 codex/<任务> 或 owner/dengbofu；禁止直接在主干开发。')


def check_message(message, generated=True):
    # Git-generated merge/revert messages are exempt; manually written titles use the policy.
    title = message.splitlines()[0] if message.splitlines() else ''
    if generated and title.startswith(('Merge ', 'Revert "')):
        return
    if not TITLE.fullmatch(title) or not re.search(r'[\u3400-\u9fff]', title):
        raise ValueError('标题须为 <type>(<可选scope>): <中文主题>，例如 fix(goods): 修复库存显示。')
    if len(title) > 100:
        raise ValueError('提交或 PR 标题不能超过 100 个字符。')


def blob(revision, path):
    return git('show', '{}:{}'.format(revision, path))


def files_at(revision):
    args = ('ls-files', '--cached', '-z') if revision == '' else ('ls-tree', '-r', '--name-only', '-z', revision)
    return [p for p in git(*args).decode('utf-8').split('\0') if p]


def changed(base, revision):
    args = ['diff', '--name-status', '--no-renames', '-z']
    args += ['--cached', base] if revision == '' else [base, revision]
    fields = git(*args).decode('utf-8').split('\0')
    return list(zip(fields[0:-1:2], fields[1:-1:2]))


def registry(revision):
    data = json.loads(blob(revision, 'versions/modules.json').decode('utf-8'))
    if data.get('schema_version') != 1:
        raise ValueError('不支持的模块清单版本。')
    modules = data['modules']
    for name, module in modules.items():
        if not SEMVER.fullmatch(module['version']):
            raise ValueError('模块版本格式错误：' + name)
    return modules


def owner(path, modules):
    matches = [(len(prefix), name) for name, module in modules.items()
               for prefix in module['paths']
               if path == prefix or path.startswith(prefix.rstrip('/') + '/')]
    return max(matches)[1] if matches else None


def forbidden(path):
    p = PurePosixPath(path)
    return ((p.name == '.env' or p.name.startswith('.env.'))
            and p.name not in ('.env.example', '.env.postgres.example')) or (
                p.suffix.lower() in ('.pem', '.key') and 'private' in p.name.lower()) or (
                any(part in ('node_modules', '__pycache__', '.venv', 'venv') for part in p.parts))


def check(base='HEAD', revision='', syntax=False):
    if output('ls-files', '--unmerged'):
        raise ValueError('存在未解决的合并冲突。')
    changes = changed(base, revision)
    args = ['diff', '--check'] + (['--cached', base] if revision == '' else [base, revision])
    modules = registry(revision)
    paths = files_at(revision)
    old_modules = registry(base)
    if set(old_modules) - set(modules):
        raise ValueError('移除已登记模块须由维护者单独制定迁移方案。')
    all_paths = set(paths)
    changed_names = {path for _, path in changes}
    migration_numbers = set()
    for path in paths:
        if owner(path, modules) is None:
            raise ValueError('文件未登记模块归属：' + path)
        match = MIGRATION.fullmatch(path)
        if match:
            key = (match[1], int(match[2]))
            if key in migration_numbers:
                raise ValueError('Django Migration 编号重复：' + path)
            migration_numbers.add(key)
    for name, module in modules.items():
        if set(module['dependencies']) - set(modules):
            raise ValueError('未知模块依赖：' + name)
        if 'versions/changelogs/' + name + '.md' not in all_paths:
            raise ValueError('模块缺少 changelog：' + name)
        if name in old_modules and tuple(map(int, module['version'].split('.'))) < tuple(
                map(int, old_modules[name]['version'].split('.'))):
            raise ValueError('模块版本不得降低：' + name)
        if (name not in old_modules or module['version'] != old_modules[name]['version']) and (
                'versions/changelogs/' + name + '.md' not in changed_names):
            raise ValueError('模块升版须同时提交模块 changelog：' + name)
    checked = 0
    for status, path in changes:
        if MIGRATION.fullmatch(path) and status != 'A':
            raise ValueError('禁止修改、删除或重命名已有 Django Migration：' + path)
        module = owner(path, modules) or owner(path, old_modules)
        # Documentation and version metadata do not independently require a release bump.
        if PurePosixPath(path).suffix in ('.py', '.js', '.css', '.html', '.sh', '.ps1', '.yml', '.yaml'):
            if module in old_modules and modules[module]['version'] == old_modules[module]['version']:
                raise ValueError('实现变更须升级模块版本：' + module)
            if 'versions/changelogs/' + module + '.md' not in changed_names:
                raise ValueError('实现变更须同时提交模块 changelog：' + module)
        if status == 'D':
            continue
        if forbidden(path):
            raise ValueError('禁止纳入本地配置、私钥或生成文件：' + path)
        content = blob(revision, path)
        if b'\0' not in content:
            text = content.decode('utf-8-sig', errors='replace')
            if re.search(r'^(<<<<<<< |>>>>>>> )', text, re.M):
                raise ValueError('文件含冲突标记：' + path)
        if not syntax:
            continue
        if path.endswith('.py'):
            ast.parse(content, filename=path)
            checked += 1
        elif path.endswith('.js'):
            # Validate the exact index/commit bytes, including partially staged files.
            with tempfile.TemporaryDirectory(prefix='tea_saas-js-') as directory:
                target = Path(directory) / 'check.js'
                target.write_bytes(content)
                subprocess.run(['node', '--check', str(target)], check=True, capture_output=True)
            checked += 1
    git(*args)
    print('OK: {} changed files; {} modules; {} Python/JS syntax checks'.format(
        len(changes), len(modules), checked))
    if syntax:
        print('STATIC CHECK PASSED / Django、模板、数据库与业务验证须另行记录。')


def pre_push(remote, stream):
    if remote != 'origin':
        raise ValueError('交付只允许向 origin 推送。')
    if output('remote', 'get-url', '--push', 'origin') not in (
            'https://github.com/dengbofu-git/shop.git', 'https://github.com/dengbofu-git/shop',
            'git@github.com:dengbofu-git/shop.git'):
        raise ValueError('origin 推送地址必须指向 dengbofu-git/shop。')
    require_branch()
    if output('status', '--porcelain', '--untracked-files=all'):
        raise ValueError('推送前须精确提交授权改动并保持工作区干净，禁止自动 stash 或清理他人工作。')
    git('fetch', '--no-tags', 'origin', 'refs/heads/main:refs/remotes/origin/main')
    head = output('rev-parse', 'HEAD')
    target = output('rev-parse', 'refs/remotes/origin/main')
    if output('merge-base', target, head) != target:
        raise ValueError('先将最新 origin/main 正常 merge 到开发分支，再重验并推送。')
    records = [line.split() for line in stream if line.strip()]
    if not records:
        raise ValueError('没有可校验的推送对象。')
    branch = output('branch', '--show-current')
    for local_ref, sha, remote_ref, remote_sha in records:
        if sha == '0' * 40:
            raise ValueError('删除远端引用请由维护者单独审核处理。')
        if remote_ref.startswith('refs/tags/'):
            if remote_sha != '0' * 40 and remote_sha != sha:
                raise ValueError('禁止覆盖已有远端标签。')
            tag = remote_ref[len('refs/tags/'):]
            modules = registry(head)
            valid = {name + '/v' + module['version'] for name, module in modules.items()}
            if tag not in valid or output('cat-file', '-t', sha) != 'tag':
                raise ValueError('发布须使用匹配模块当前版本的注释标签。')
            commit = output('rev-parse', sha + '^{commit}')
            if output('merge-base', commit, target) != commit:
                raise ValueError('标签必须指向已进入 origin/main 的提交。')
            tagged = registry(commit)
            if tag not in {name + '/v' + module['version'] for name, module in tagged.items()}:
                raise ValueError('标签版本与标签提交中的版本清单不一致。')
        elif (remote_ref != 'refs/heads/' + branch or local_ref != 'refs/heads/' + branch or sha != head):
            raise ValueError('只允许推送当前开发分支的最终 HEAD；禁止直接推送 main 或其他分支。')
        elif remote_sha != '0' * 40:
            git('fetch', '--no-tags', 'origin', remote_ref)
            if output('merge-base', remote_sha, head) != remote_sha:
                raise ValueError('禁止非快进推送；先正常 merge 远端同名分支。')
    check(target, head, syntax=True)
    # Recheck freshness after potentially slow checks.
    latest = output('ls-remote', '--heads', 'origin', 'refs/heads/main').split()[0]
    if latest != target or output('rev-parse', 'HEAD') != head or output('status', '--porcelain'):
        raise ValueError('检查期间 main、HEAD 或工作区变化，须重新同步和验证。')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('install', help='Enable repository-local hooks')
    for name in ('check', 'verify'):
        sub = commands.add_parser(name)
        sub.add_argument('--base', help='Committed baseline; omit to check the exact staged snapshot')
        sub.add_argument('--head', default='HEAD')
        sub.add_argument('--branch', help='Explicit source branch for detached CI checkout')
    message = commands.add_parser('message')
    message.add_argument('--file')
    message.add_argument('--text')
    push = commands.add_parser('pre-push')
    push.add_argument('remote')
    args = parser.parse_args()
    if args.command == 'install':
        existing = output('config', '--local', '--get-regexp', '^core\\.hooksPath$') if subprocess.run(
            ['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'config', '--local', '--get', 'core.hooksPath'],
            cwd=ROOT, stdout=subprocess.DEVNULL).returncode == 0 else ''
        if existing and existing.split(maxsplit=1)[1] != '.githooks':
            raise ValueError('已有 hooksPath，先人工核对，不能覆盖：' + existing)
        template = subprocess.run(
            ['git', '-c', 'safe.directory=' + ROOT.as_posix(), 'config', '--local', '--get', 'commit.template'],
            cwd=ROOT, capture_output=True, text=True)
        if template.returncode == 0 and template.stdout.strip() != '.gitmessage':
            raise ValueError('已有 commit.template，先人工核对，不能覆盖。')
        git('config', '--local', 'core.hooksPath', '.githooks')
        git('config', '--local', 'commit.template', '.gitmessage')
        if os.name != 'nt':
            for name in ('pre-commit', 'commit-msg', 'pre-push'):
                (ROOT / '.githooks' / name).chmod(0o755)
        print('Enabled: core.hooksPath=.githooks; commit.template=.gitmessage (local clone only)')
    elif args.command == 'message':
        check_message(Path(args.file).read_text(encoding='utf-8-sig') if args.file else (args.text or ''),
                      generated=bool(args.file))
        print('OK: message')
    elif args.command == 'pre-push':
        pre_push(args.remote, sys.stdin)
    else:
        require_branch(args.branch)
        check(args.base or 'HEAD', args.head if args.base else '', syntax=args.command == 'verify')


if __name__ == '__main__':
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    try:
        main()
    except (ValueError, SyntaxError, OSError, subprocess.CalledProcessError) as error:
        # Avoid dumping Git remote URLs or file contents that may contain secrets.
        print('Git policy blocked: ' + (str(error) if not isinstance(error, subprocess.CalledProcessError)
                                        else 'command failed; inspect the affected diff/tool locally'), file=sys.stderr)
        sys.exit(1)
