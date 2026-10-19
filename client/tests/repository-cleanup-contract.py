"""Offline cleanup contracts: immutable archive bytes and live static dependencies."""
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'docs/sdd/evidence/2026-10-19-repository-cleanup/static-assets.json'


class Scripts(HTMLParser):
    def __init__(self):
        super().__init__()
        self.sources = []

    def handle_starttag(self, tag, attrs):
        if tag == 'script':
            source = dict(attrs).get('src')
            if source:
                self.sources.append(source)


class RepositoryCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.assets = json.loads(ASSETS.read_text(encoding='utf-8'))

    def test_canonical_images_retain_exact_content(self):
        for alias in self.assets['image_aliases']:
            with self.subTest(path=alias['removed']):
                self.assertFalse((ROOT / alias['removed']).exists())
                self.assertEqual(hashlib.sha256((ROOT / alias['kept']).read_bytes()).hexdigest(), alias['sha256'])

    def test_live_code_does_not_reference_retired_assets(self):
        needles = [item['removed'].removeprefix('client/static/') for item in self.assets['image_aliases']]
        needles += ['css/icon/', 'js/icon/', 'jquery-3.3.1.js']
        for directory in ['client/templates', 'client/static', 'goods', 'tea_saas']:
            for path in (ROOT / directory).rglob('*'):
                if not path.is_file() or path.suffix not in ('.html', '.css', '.js', '.py'):
                    continue
                text = path.read_text(encoding='utf-8-sig', errors='replace')
                for needle in needles:
                    with self.subTest(path=path.relative_to(ROOT).as_posix(), reference=needle):
                        self.assertNotIn(needle, text)
        for path in self.assets['removed_old_components']:
            self.assertFalse((ROOT / path).exists())

    def test_payment_core_and_cookie_plugin_use_one_jquery_instance(self):
        for relative in self.assets['jquery']['templates']:
            with self.subTest(template=relative):
                parser = Scripts()
                parser.feed((ROOT / relative).read_text(encoding='utf-8'))
                versions = [source for source in parser.sources if re.search(r'/jquery-\d', source)]
                self.assertEqual(len(versions), 1)
                self.assertTrue(versions[0].endswith('/jquery-3.1.1.min.js'))
                cookie = next(source for source in parser.sources if source.endswith('/jquery.cookie.js'))
                self.assertLess(parser.sources.index(versions[0]), parser.sources.index(cookie))
                for source in [versions[0], cookie]:
                    self.assertTrue((ROOT / 'client' / source[source.index('static/'):]).is_file())
        self.assertFalse((ROOT / self.assets['jquery']['removed']).exists())

    def test_historical_payload_is_byte_identical_and_complete(self):
        data = json.loads((ROOT / self.assets['archive_manifest']).read_text(encoding='utf-8'))
        self.assertEqual(len(data['files']), self.assets['archived_files'])
        self.assertEqual(len({record['original'] for record in data['files']}), len(data['files']))
        for record in data['files']:
            with self.subTest(path=record['archived']):
                self.assertEqual(hashlib.sha256((ROOT / record['archived']).read_bytes()).hexdigest(), record['sha256'])
                self.assertFalse((ROOT / record['original']).exists())
                self.assertNotIn('__pycache__', record['archived'])

    def test_current_comparison_defaults_have_their_historical_inputs(self):
        root = ROOT / 'reports/archive/2026-10-16/agent-evaluation/2026-10-16-planner'
        for name in ['historical-records.json', 'baseline-source/workflow.py', 'baseline-source/recommendations.py']:
            self.assertTrue((root / name).is_file(), name)
        relative = root.relative_to(ROOT).as_posix()
        for source in ['support_ai/evaluation/compare.py', 'support_ai/evaluation/report.py']:
            self.assertIn(relative, (ROOT / source).read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main()
