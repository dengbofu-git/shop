"""Real temporary Git repositories exercise staged/committed delivery boundaries."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('git_policy', Path(__file__).resolve().parents[1] / 'git_policy.py')
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


class SnapshotChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='tea_saas-policy-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.original_root = policy.ROOT
        policy.ROOT = self.root
        self.addCleanup(setattr, policy, 'ROOT', self.original_root)
        self.run_git('init', '-b', 'codex/core-test')
        self.write('versions/modules.json', json.dumps({'schema_version': 1, 'modules': {
            'core': {'version': '0.1.0', 'dependencies': [], 'paths': [
                'app/', 'versions/', 'docs/', '.env', '.env.local', '.env.example']}}}))
        self.write('versions/changelogs/core.md', '# Core\n')
        self.write('app/code.py', 'value = 1\n')
        self.write('app/migrations/0001_initial.py', 'initial = True\n')
        self.run_git('add', '.')
        self.commit()

    def run_git(self, *args):
        return subprocess.check_output([
            'git', '-c', 'safe.directory=' + self.root.as_posix(),
            '-c', 'core.autocrlf=false', '-c', 'user.name=Policy Test',
            '-c', 'user.email=policy-test@example.invalid', *args], cwd=self.root,
            stderr=subprocess.PIPE).decode('utf-8').strip()

    def commit(self):
        self.run_git('-c', 'core.hooksPath=disabled-hooks', 'commit', '-m', 'test(core): 初始快照')

    def write(self, path, content):
        target = self.root / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content.encode('utf-8'))

    def bump(self):
        path = self.root / 'versions/modules.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['modules']['core']['version'] = '0.1.1'
        self.write('versions/modules.json', json.dumps(data))
        self.write('versions/changelogs/core.md', '# Core\n\n## 0.1.1\n- Change\n')
        self.run_git('add', 'versions')

    def check(self, *args, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            policy.check(*args, **kwargs)

    def test_partial_stage_reads_index_not_working_file(self):
        self.bump()
        self.write('app/code.py', 'value = 2\n')
        self.run_git('add', 'app/code.py')
        self.write('app/code.py', 'this is invalid python !!!\n')
        self.check(syntax=True)

    def test_invalid_staged_python_cannot_be_hidden_by_working_file(self):
        self.bump()
        self.write('app/code.py', 'invalid !!!\n')
        self.run_git('add', 'app/code.py')
        self.write('app/code.py', 'value = 2\n')
        with self.assertRaises(SyntaxError):
            self.check(syntax=True)

    def test_committed_check_ignores_uncommitted_repair(self):
        base = self.run_git('rev-parse', 'HEAD')
        self.bump()
        self.write('app/code.py', 'invalid !!!\n')
        self.run_git('add', 'app/code.py')
        self.commit()
        self.write('app/code.py', 'value = 2\n')
        with self.assertRaises(SyntaxError):
            self.check(base, 'HEAD', syntax=True)

    def test_implementation_without_version_is_blocked(self):
        self.write('app/code.py', 'value = 2\n')
        self.run_git('add', 'app/code.py')
        with self.assertRaisesRegex(ValueError, '升级模块版本'):
            self.check()

    def test_implementation_without_changelog_is_blocked(self):
        self.bump()
        self.run_git('restore', '--staged', 'versions/changelogs/core.md')
        self.write('app/code.py', 'value = 2\n')
        self.run_git('add', 'app/code.py')
        with self.assertRaisesRegex(ValueError, '同时提交模块 changelog'):
            self.check()

    def test_deleting_implementation_requires_version(self):
        self.run_git('rm', 'app/code.py')
        with self.assertRaisesRegex(ValueError, '升级模块版本'):
            self.check()

    def test_documentation_does_not_require_release(self):
        self.write('docs/guide.md', '# Guide\n')
        self.run_git('add', 'docs/guide.md')
        self.check()

    def test_private_environment_path_is_blocked(self):
        self.write('.env.local', 'EXAMPLE=value\n')
        self.run_git('add', '.env.local')
        with self.assertRaisesRegex(ValueError, '禁止纳入'):
            self.check()

    def test_environment_example_is_allowed(self):
        self.write('.env.example', 'EXAMPLE=\n')
        self.run_git('add', '.env.example')
        self.check()

    def test_existing_migration_edit_is_blocked(self):
        self.bump()
        self.write('app/migrations/0001_initial.py', 'initial = False\n')
        self.run_git('add', 'app/migrations')
        with self.assertRaisesRegex(ValueError, '已有 Django Migration'):
            self.check()

    def test_existing_migration_deletion_is_blocked(self):
        self.run_git('rm', 'app/migrations/0001_initial.py')
        with self.assertRaisesRegex(ValueError, '已有 Django Migration'):
            self.check()

    def test_duplicate_migration_numbers_are_blocked(self):
        self.bump()
        self.write('app/migrations/0001_other.py', 'value = 1\n')
        self.run_git('add', 'app/migrations')
        with self.assertRaisesRegex(ValueError, '编号重复'):
            self.check()

    def test_new_migration_is_allowed(self):
        self.bump()
        self.write('app/migrations/0002_next.py', 'value = 2\n')
        self.run_git('add', 'app/migrations')
        self.check(syntax=True)

    def test_unowned_file_is_blocked(self):
        self.write('unknown.txt', 'example\n')
        self.run_git('add', 'unknown.txt')
        with self.assertRaisesRegex(ValueError, '未登记模块归属'):
            self.check()

    def test_conflict_marker_is_blocked(self):
        self.write('docs/guide.md', '<<<<<<< HEAD\nexample\n')
        self.run_git('add', 'docs/guide.md')
        with self.assertRaisesRegex(ValueError, '冲突标记'):
            self.check()

    def test_downgrade_is_blocked(self):
        data = json.loads((self.root / 'versions/modules.json').read_text(encoding='utf-8'))
        data['modules']['core']['version'] = '0.0.9'
        self.write('versions/modules.json', json.dumps(data))
        self.run_git('add', 'versions/modules.json')
        with self.assertRaisesRegex(ValueError, '不得降低'):
            self.check()

    def test_install_preserves_existing_hooks_configuration(self):
        self.run_git('config', '--local', 'core.hooksPath', 'existing-hooks')
        with patch.object(policy.sys, 'argv', ['git_policy.py', 'install']):
            with self.assertRaisesRegex(ValueError, '已有 hooksPath'):
                policy.main()
        self.assertEqual(self.run_git('config', '--local', '--get', 'core.hooksPath'), 'existing-hooks')


class IdentityChecks(unittest.TestCase):
    def test_chinese_conventional_title(self):
        policy.check_message('fix(goods): 修复库存显示')
        policy.check_message('docs: 更新文档')

    def test_english_or_untyped_title_is_rejected(self):
        for title in ('fix(goods): repair stock', '修复库存', ''):
            with self.subTest(title=title), self.assertRaises(ValueError):
                policy.check_message(title)

    def test_generated_merge_allowed_only_for_commit(self):
        policy.check_message("Merge branch 'main'")
        with self.assertRaises(ValueError):
            policy.check_message("Merge branch 'main'", generated=False)

    def test_protected_and_unregistered_branches_are_rejected(self):
        for branch in ('main', 'master', 'dev', '', 'owner/unknown'):
            with self.subTest(branch=branch), self.assertRaises(ValueError):
                policy.require_branch(branch)
        policy.require_branch('codex/core-policy')
        policy.require_branch('owner/dengbofu')

    def test_dirty_push_is_rejected_before_network(self):
        def answer(*args):
            if args[:2] == ('remote', 'get-url'):
                return 'https://github.com/dengbofu-git/shop.git'
            if args[0] == 'status':
                return ' M app/code.py'
            return 'codex/core-policy'
        with patch.object(policy, 'output', side_effect=answer), patch.object(policy, 'git') as git:
            with self.assertRaisesRegex(ValueError, '工作区干净'):
                policy.pre_push('origin', [])
            git.assert_not_called()

    def test_main_push_is_rejected_before_network(self):
        def answer(*args):
            if args[0] == 'remote':
                return 'https://github.com/dengbofu-git/shop.git'
            return 'main'
        with patch.object(policy, 'output', side_effect=answer), patch.object(policy, 'git') as git:
            with self.assertRaises(ValueError):
                policy.pre_push('origin', [])
            git.assert_not_called()


if __name__ == '__main__':
    unittest.main()
