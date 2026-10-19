"""合成目录验证引用边界、扫描范围、截断及失败状态，不读取业务数据。"""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from tools import sdd_refs


class SddReferencesTests(unittest.TestCase):
    def setUp(self):
        # 将合成夹具放在仓库内，兼容宿主临时目录不可写的沙箱。
        scratch = (sdd_refs.ROOT / '.scratch').resolve()
        scratch.mkdir(exist_ok=True)
        self.folder = tempfile.TemporaryDirectory(prefix='sdd-refs-', dir=scratch)
        self.root = Path(self.folder.name).resolve()
        self.root.relative_to(scratch)  # 确认自动清理范围始终在本次夹具根内。
        self.addCleanup(self.folder.cleanup)
        (self.root / 'docs/sdd').mkdir(parents=True)

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        return path

    def run_cli(self, *args):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            code = sdd_refs.main(args, root=self.root)
        return code, output.getvalue(), errors.getvalue()

    def test_identifier_boundaries_unicode_and_line_numbers(self):
        self.write('docs/sdd/a.md', '\ufeff标题\n中文（CAP-AI-003），`CAP-AI-003`\n'
                   'CAP-AI-003-01 CAP-AI-003-A XCAP-AI-003 CAP-AI-003_extra\n')
        matches, total = sdd_refs.find_references(self.root, 'CAP-AI-003')
        self.assertEqual(total, 1)
        self.assertEqual(matches, [('docs/sdd/a.md', 2, '中文（CAP-AI-003），`CAP-AI-003`')])

    def test_scope_extensions_and_evidence_opt_in(self):
        for name in ('docs/sdd/a.md', 'docs/sdd/b.yaml', 'docs/sdd/c.yml', 'docs/sdd/d.json',
                     'docs/sdd/evidence/run/a.md', 'docs/sdd/a.py', 'docs/adr/a.md',
                     '.scratch/a/spec.md', 'docs/sdd/.hidden/a.md', 'docs/sdd/node_modules/a.md'):
            self.write(name, 'CAP-AI-003')
        self.assertEqual(sdd_refs.find_references(self.root, 'CAP-AI-003')[1], 4)
        self.assertEqual(sdd_refs.find_references(self.root, 'CAP-AI-003', include_evidence=True)[1], 5)

    def test_sorted_output_truncation_and_total_lines(self):
        self.write('docs/sdd/z.md', 'CAP-AI-003')
        self.write('docs/sdd/a.md', 'CAP-AI-003\nCAP-AI-003')
        code, output, errors = self.run_cli('CAP-AI-003', '--limit', '1')
        self.assertEqual(code, 0)
        self.assertTrue(output.startswith('docs/sdd/a.md:1: CAP-AI-003\n'))
        self.assertIn('显示 1 / 3', output)
        self.assertEqual(errors, '')

    def test_no_match_and_invalid_arguments_have_distinct_status(self):
        code, output, errors = self.run_cli('CAP-AI-003')
        self.assertEqual(code, 1)
        self.assertIn('无引用', output)
        self.assertEqual(errors, '')
        for args in (('../CAP-AI-003',), ('CAP-AI-003.*',), ('CAP-AI-003', '--limit', '0'),
                     ('CAP-AI-003', '--limit', 'bad')):
            with self.subTest(args=args), self.assertRaises(SystemExit) as raised:
                self.run_cli(*args)
            self.assertEqual(raised.exception.code, 2)

    def test_missing_directory_is_an_error(self):
        (self.root / 'docs/sdd').rmdir()
        code, output, errors = self.run_cli('CAP-AI-003')
        self.assertEqual(code, 2)
        self.assertEqual(output, '')
        self.assertIn('失败', errors)

    def test_decode_and_read_failures_do_not_report_partial_success(self):
        self.write('docs/sdd/a.md', 'CAP-AI-003')
        path = self.write('docs/sdd/z.md', '')
        path.write_bytes(b'\xff\xfe')
        code, output, errors = self.run_cli('CAP-AI-003')
        self.assertEqual(code, 2)
        self.assertEqual(output, '')
        self.assertIn('UnicodeDecodeError', errors)
        with patch.object(Path, 'read_text', side_effect=PermissionError):
            code, output, errors = self.run_cli('CAP-AI-003')
        self.assertEqual((code, output), (2, ''))
        self.assertIn('PermissionError', errors)

    def test_links_are_not_followed(self):
        target = self.write('outside/a.md', 'CAP-AI-003')
        try:
            (self.root / 'docs/sdd/link.md').symlink_to(target)
            (self.root / 'docs/sdd/linked-dir').symlink_to(target.parent, target_is_directory=True)
        except OSError as error:
            self.skipTest('当前宿主不允许创建测试符号链接：{}'.format(type(error).__name__))
        self.assertEqual(sdd_refs.find_references(self.root, 'CAP-AI-003'), ([], 0))


if __name__ == '__main__':
    unittest.main()
