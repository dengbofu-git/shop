"""Keep the product namespace consistent across current repository source files."""
import hashlib
import re
import unittest

from tools.module_versions import ROOT, working_paths


# These two immutable migrations predate the product namespace. Only their
# exact original contents are exempt, never an entire migrations directory.
HISTORICAL_CONTENTS = {
    'users/migrations/0006_create_admin_user.py': 'c58dc05d9243a07708e5038a5d212504c7dba58f2cb7afbefd14eb60cdfd5974',
    'users/migrations/0007_create_customs_user.py': '18c0e80f1059a3a2227f5d30b0f8f55dc7f7bce5c4bf0d05516e64fac19f4b79',
}
RETIRED_NAMESPACE = re.compile('dada' + 'shop' + '|\u8317\u8d8a\u5c71\u5173', re.IGNORECASE)


def namespace_violations(name, raw):
    violations = [name + ': path'] if RETIRED_NAMESPACE.search(name) else []
    if b'\x00' in raw:
        if name in HISTORICAL_CONTENTS:
            violations.append(name + ': immutable historical content changed')
        return violations
    try:
        content = raw.decode('utf-8-sig').replace('\r\n', '\n')
    except UnicodeDecodeError:
        if name in HISTORICAL_CONTENTS:
            violations.append(name + ': immutable historical content changed')
        return violations
    if name in HISTORICAL_CONTENTS:
        digest = hashlib.sha256(content.encode('utf-8')).hexdigest()
        if digest == HISTORICAL_CONTENTS[name]:
            return violations
        violations.append(name + ': immutable historical content changed')
    if RETIRED_NAMESPACE.search(content):
        violations.append(name + ': content')
    return violations


class ProjectIdentityTests(unittest.TestCase):
    def test_current_file_names_and_utf8_contents_use_current_namespace(self):
        violations = []
        for name in working_paths():
            violations.extend(namespace_violations(name, (ROOT / name).read_bytes()))
        self.assertEqual(violations, [])

    def test_historical_exception_rejects_any_content_change(self):
        for name in HISTORICAL_CONTENTS:
            raw = (ROOT / name).read_bytes()
            self.assertEqual(namespace_violations(name, raw), [])
            self.assertEqual(namespace_violations(name, raw.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')), [])
            self.assertIn(name + ': immutable historical content changed',
                          namespace_violations(name, raw + b'# unexpected change\n'))
            for suffix in (b'\x00', b'\xff'):
                self.assertIn(name + ': immutable historical content changed',
                              namespace_violations(name, raw + suffix))

    def test_new_migrations_and_current_source_cannot_use_retired_namespace(self):
        old = ('dada' + 'shop').encode('ascii')
        for name in ('users/migrations/0099_new.py', 'tea_saas/new.py'):
            self.assertIn(name + ': content', namespace_violations(name, old))

    def test_entrypoints_and_tool_package_exist(self):
        for name in ('tea_saas/settings.py', 'tea_saas/urls.py', 'tea_saas/wsgi.py',
                     'tea_saas/asgi.py', 'tools/tea_saas_mcp/server.py',
                     '.agents/skills/tea-saas-change-delivery/SKILL.md'):
            self.assertTrue((ROOT / name).is_file(), name)
        self.assertIn('tea_saas.settings', (ROOT / 'manage.py').read_text(encoding='utf-8'))
