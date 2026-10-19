"""Working-tree ownership must handle unstaged directory renames without Git writes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import module_versions


class WorkingTreeOwnershipTests(unittest.TestCase):
    def test_deleted_paths_are_excluded_and_new_untracked_paths_are_checked(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'tea_saas').mkdir()
            (root / 'tea_saas/settings.py').write_text('# synthetic', encoding='utf-8')
            (root / 'README.md').write_text('synthetic', encoding='utf-8')
            with patch.object(module_versions, 'ROOT', root), patch.object(
                    module_versions, 'git', side_effect=['retired/settings.py\0README.md\0', 'tea_saas/settings.py\0']):
                self.assertEqual(module_versions.working_paths(), ['README.md', 'tea_saas/settings.py'])
            modules = {'core': {'paths': ['tea_saas/', 'README.md']}}
            self.assertEqual(module_versions.owner('tea_saas/settings.py', modules), 'core')
            self.assertIsNone(module_versions.owner('unowned.txt', modules))

    def test_deleted_only_and_empty_git_output(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(module_versions, 'ROOT', Path(folder)), patch.object(
                    module_versions, 'git', side_effect=['retired.txt\0', '']):
                self.assertEqual(module_versions.working_paths(), [])
