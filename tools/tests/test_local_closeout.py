"""Synthetic Git fixtures only; never uses the actual project repository."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

from tools.local_closeout import create_plan, apply_plan, recover_before_switch, digest, git, snapshot, safe_file, UnsafeCloseout
from tools.local_closeout import create_retirement_plan, retire_workspace


class PromotionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.parent = Path(self.temp.name)
        self.root = self.parent / 'primary'
        self.root.mkdir()
        git(self.root, 'init', '-b', 'codex/original')
        git(self.root, 'config', 'user.name', 'Synthetic Audit')
        git(self.root, 'config', 'user.email', 'audit@example.invalid')
        (self.root / '.gitignore').write_text('.env\nmedia/\n.scratch/\n')
        (self.root / 'app.py').write_text('old = True\n')
        (self.root / 'retired.py').write_text('legacy = True\n')
        migration = self.root / 'app/migrations/0001_initial.py'
        migration.parent.mkdir(parents=True)
        migration.write_text('# immutable synthetic migration\n')
        git(self.root, 'add', '--', '.gitignore', 'app.py', 'retired.py', 'app/migrations/0001_initial.py')
        git(self.root, 'commit', '-m', 'synthetic initial fixture')
        git(self.root, 'switch', '-c', 'main')
        (self.root / 'app.py').write_text('reviewed = True\n')
        (self.root / 'retired.py').unlink()
        (self.root / 'reviewed.py').write_text('stock_lock = True\n')
        git(self.root, 'add', '--', 'app.py', 'retired.py', 'reviewed.py')
        git(self.root, 'commit', '-m', 'synthetic reviewed fixture')
        self.source = self.parent / 'integrated'
        git(self.root, 'worktree', 'add', '--detach', str(self.source), 'main')
        git(self.root, 'switch', 'codex/original')
        (self.root / 'app.py').write_text('unsubmitted_original = True\n')
        (self.root / 'untracked.py').write_text('saved_proposal = True\n')
        (self.root / '.env').write_text('SYNTHETIC=retained\n')
        (self.root / 'media').mkdir()
        (self.root / 'media/private.bin').write_bytes(b'synthetic-media')
        (self.source / 'app.py').write_text('reviewed = True\nlocal_feature = True\n')
        (self.source / 'local.py').write_text('streaming = True\n')
        self.original_bytes = {name: (self.root / name).read_bytes() for name in ('app.py', 'untracked.py')}
        self.recovery = self.parent / 'recovery'

    def plan(self):
        return create_plan(self.root, self.source, self.recovery, 'codex/unified', 'main')

    def apply(self, expected):
        return apply_plan(self.recovery / 'plan.json', expected)

    def test_promotes_main_and_local_preserving_recovery_assets_and_history(self):
        plan, expected = self.plan()
        self.apply(expected)
        self.assertEqual((self.root / 'app.py').read_text(), 'reviewed = True\nlocal_feature = True\n')
        self.assertTrue((self.root / 'reviewed.py').exists())
        self.assertTrue((self.root / 'local.py').exists())
        self.assertFalse((self.root / 'retired.py').exists())
        self.assertEqual((self.root / '.env').read_text(), 'SYNTHETIC=retained\n')
        self.assertEqual((self.root / 'media/private.bin').read_bytes(), b'synthetic-media')
        self.assertEqual(git(self.root, 'rev-parse', 'HEAD').decode().strip(), plan['main'])
        self.assertEqual(git(self.root, 'diff', '--cached'), b'')
        with zipfile.ZipFile(self.recovery / 'primary-before.zip') as z:
            self.assertEqual(z.read('app.py'), self.original_bytes['app.py'])
            self.assertEqual(z.read('untracked.py'), self.original_bytes['untracked.py'])
        self.assertEqual(json.loads((self.recovery / 'journal.json').read_text())[-1]['state'], 'complete')

    def test_new_primary_edit_invalidates_plan_without_writes(self):
        _, expected = self.plan()
        (self.root / 'app.py').write_text('new_edit = True\n')
        before = snapshot(self.root)
        with self.assertRaises(UnsafeCloseout): self.apply(expected)
        self.assertEqual(snapshot(self.root), before)

    def test_new_integrated_edit_invalidates_plan(self):
        _, expected = self.plan()
        (self.source / 'local.py').write_text('new = True\n')
        before = snapshot(self.root)
        with self.assertRaises(UnsafeCloseout): self.apply(expected)
        self.assertEqual(snapshot(self.root), before)

    def test_changed_plan_hash_is_rejected(self):
        self.plan()
        before = snapshot(self.root)
        with self.assertRaises(UnsafeCloseout): self.apply('not-the-reviewed-hash')
        self.assertEqual(snapshot(self.root), before)

    def test_corrupt_backup_is_rejected(self):
        _, expected = self.plan()
        with (self.recovery / 'primary-before.zip').open('ab') as f: f.write(b'changed')
        before = snapshot(self.root)
        with self.assertRaises(UnsafeCloseout): self.apply(expected)
        self.assertEqual(snapshot(self.root), before)

    def test_staged_intent_is_rejected(self):
        git(self.root, 'add', '--', 'app.py')
        with self.assertRaises(UnsafeCloseout): self.plan()

    def test_existing_branch_is_rejected(self):
        git(self.root, 'branch', 'codex/unified')
        with self.assertRaises(UnsafeCloseout): self.plan()

    def test_source_must_match_reviewed_base(self):
        with self.assertRaises(UnsafeCloseout):
            create_plan(self.root, self.source, self.recovery, 'codex/new', 'codex/original')

    def test_linked_root_is_rejected(self):
        with patch.object(Path, 'is_symlink', return_value=True):
            with self.assertRaises(UnsafeCloseout): self.plan()

    def test_traversal_is_rejected(self):
        with self.assertRaises(UnsafeCloseout): safe_file(self.root, '../outside')

    def test_modified_migration_is_rejected(self):
        (self.source / 'app/migrations/0001_initial.py').write_text('# changed\n')
        with self.assertRaises(UnsafeCloseout): self.plan()

    def test_added_migration_is_rejected(self):
        (self.source / 'app/migrations/0002_unreviewed.py').write_text('# new\n')
        with self.assertRaises(UnsafeCloseout): self.plan()

    def test_attempted_plan_is_not_replayed(self):
        _, expected = self.plan()
        self.apply(expected)
        with self.assertRaises(UnsafeCloseout): self.apply(expected)

    def test_changed_main_is_rejected(self):
        _, expected = self.plan()
        real = git
        def changed(root, *args):
            return b'changed-main\n' if args == ('rev-parse', 'main') else real(root, *args)
        with patch('tools.local_closeout.git', side_effect=changed):
            with self.assertRaises(UnsafeCloseout): self.apply(expected)

    def test_pre_checkout_failure_can_recover_original_bytes(self):
        plan, expected = self.plan()
        real = git
        def stopped(root, *args):
            if 'switch' in args:
                raise UnsafeCloseout('synthetic checkout refusal')
            return real(root, *args)
        with patch('tools.local_closeout.git', side_effect=stopped):
            with self.assertRaises(UnsafeCloseout): self.apply(expected)
        recover_before_switch(self.recovery / 'plan.json', expected)
        self.assertEqual(snapshot(self.root)['files'], plan['primary']['files'])

    def test_recovery_preserves_new_edit_and_refuses_overwrite(self):
        _, expected = self.plan()
        real = git
        def stopped(root, *args):
            if 'switch' in args:
                raise UnsafeCloseout('synthetic checkout refusal')
            return real(root, *args)
        with patch('tools.local_closeout.git', side_effect=stopped):
            with self.assertRaises(UnsafeCloseout): self.apply(expected)
        (self.root / 'app.py').write_text('new_after_failure = True\n')
        before = snapshot(self.root)
        with self.assertRaises(UnsafeCloseout): recover_before_switch(self.recovery / 'plan.json', expected)
        self.assertEqual(snapshot(self.root), before)

    def test_autocrlf_does_not_change_historical_blob_during_switch(self):
        git(self.root, 'config', 'core.autocrlf', 'true')
        _, expected = self.plan()
        self.apply(expected)
        self.assertIn('local_feature', (self.root / 'app.py').read_text())


class RetirementTests(unittest.TestCase):
    setUp = PromotionTests.setUp

    def retirement(self):
        folder = self.parent / 'retirement'
        checksum = create_retirement_plan(self.root, self.source, folder, 'main')
        return folder, checksum

    def test_reviewed_copy_is_archived_then_normally_removed(self):
        (self.source / '.env').write_text('SYNTHETIC=keep-original\n')
        original = (self.source / 'local.py').read_bytes()
        folder, checksum = self.retirement()
        with patch('tools.local_closeout.in_use', return_value=False):
            retire_workspace(folder / 'retirement.json', checksum)
        self.assertFalse(self.source.exists())
        self.assertTrue(self.root.exists())
        with zipfile.ZipFile(folder / 'workspace-before.zip') as z:
            self.assertEqual(z.read('local.py'), original)
            self.assertEqual(z.read('.env').decode().strip(), 'SYNTHETIC=keep-original')

    def test_primary_workspace_cannot_be_retired(self):
        with self.assertRaises(UnsafeCloseout):
            create_retirement_plan(self.root, self.root, self.parent / 'forbidden', 'main')

    def test_new_edit_invalidates_retirement(self):
        folder, checksum = self.retirement()
        (self.source / 'local.py').write_text('new_work = True\n')
        before = snapshot(self.source)
        with patch('tools.local_closeout.in_use', return_value=False), self.assertRaises(UnsafeCloseout):
            retire_workspace(folder / 'retirement.json', checksum)
        self.assertEqual(snapshot(self.source), before)

    def test_active_service_blocks_retirement(self):
        folder, checksum = self.retirement()
        with patch('tools.local_closeout.in_use', return_value=True), self.assertRaises(UnsafeCloseout):
            retire_workspace(folder / 'retirement.json', checksum)
        self.assertTrue(self.source.exists())

    def test_ignored_asset_edit_blocks_retirement(self):
        (self.source / '.env').write_text('SYNTHETIC=before\n')
        folder, checksum = self.retirement()
        (self.source / '.env').write_text('SYNTHETIC=changed\n')
        with patch('tools.local_closeout.in_use', return_value=False), self.assertRaises(UnsafeCloseout):
            retire_workspace(folder / 'retirement.json', checksum)
        self.assertTrue(self.source.exists())

    def test_unique_unmerged_commit_is_not_retired(self):
        git(self.source, 'add', '--', 'local.py')
        git(self.source, 'commit', '-m', 'synthetic unique work')
        with self.assertRaises(UnsafeCloseout): self.retirement()


if __name__ == '__main__':
    unittest.main()
