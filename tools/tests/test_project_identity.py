"""Keep the product namespace consistent across current repository source files."""
import re
import unittest

from tools.module_versions import ROOT, working_paths


class ProjectIdentityTests(unittest.TestCase):
    def test_current_file_names_and_utf8_contents_use_current_namespace(self):
        retired = re.compile('dada' + 'shop' + '|\u8317\u8d8a\u5c71\u5173', re.IGNORECASE)
        violations = []
        for name in working_paths():
            if retired.search(name):
                violations.append(name + ': path')
            raw = (ROOT / name).read_bytes()
            if b'\x00' in raw:
                continue
            try:
                content = raw.decode('utf-8-sig')
            except UnicodeDecodeError:
                continue
            if retired.search(content):
                violations.append(name + ': content')
        self.assertEqual(violations, [])

    def test_entrypoints_and_tool_package_exist(self):
        for name in ('tea_saas/settings.py', 'tea_saas/urls.py', 'tea_saas/wsgi.py',
                     'tea_saas/asgi.py', 'tools/tea_saas_mcp/server.py',
                     '.agents/skills/tea-saas-change-delivery/SKILL.md'):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertIn('tea_saas.settings', (ROOT / 'manage.py').read_text(encoding='utf-8'))
