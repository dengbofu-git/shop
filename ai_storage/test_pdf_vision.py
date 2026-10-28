"""真实 PDF/Tokenizer 加模拟模型的离线管道验收，不访问业务数据库。"""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import uuid

from ai_storage.pdf_pipeline import parser
from ai_storage.pdf_pipeline.chunking import make_chunks
from ai_storage.test_vision import TABLE, VisionHttpFixture, reply
from ai_storage.vision.config import freeze
from ai_storage.vision.pipeline import VisionPageProcessor, table_text


HAS_PDF = importlib.util.find_spec('fitz') is not None and importlib.util.find_spec('tokenizers') is not None
TOKENIZER_PATH = os.getenv('AI_PDF_TOKENIZER_PATH', '/models/bge-m3/tokenizer.json')


@unittest.skipUnless(HAS_PDF and Path(TOKENIZER_PATH).is_file(), 'PDF worker dependencies required')
class PdfVisionIntegrationTests(VisionHttpFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        VisionHttpFixture.setUpClass.__func__(cls)
        from tokenizers import Tokenizer
        cls.tokenizer = Tokenizer.from_file(TOKENIZER_PATH)

    def test_pdf_table_to_model_to_row_chunks_preserves_provenance(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'source.pdf'
            with fitz.open() as doc:
                page = doc.new_page(width=600, height=800)
                page.insert_text((50, 80), 'Original reliable tea report body remains searchable.')
                for x in (50, 250, 400, 550):
                    page.draw_line((x, 230), (x, 320))
                for y in (230, 260, 290, 320):
                    page.draw_line((50, y), (550, y))
                for y, cells in [(250, ['Country', '2013 estimated', '2023 projected']),
                                 (280, ['Iran', '83000', '115808']), (310, ['Turkey', '228026', '259503'])]:
                    for x, text in zip((60, 260, 410), cells):
                        page.insert_text((x, y), text)
                doc.save(source)
            config = {'max_pages': 200, 'dpi': 200, 'max_pixels': 24000000, 'ocr_timeout': 45,
                      'languages': 'eng', 'min_confidence': 70, 'ocr_mode': 'auto',
                      'vision_render_path': str(root/'vision.png')}
            with redirect_stdout(io.StringIO()):
                parsed = parser.parse(str(source), 1, str(root/'preview.png'), config)
            self.assertIn('table_extract', parsed['vision_candidates'])
            self.assertTrue((root/'vision.png').is_file())
            env = {'AI_VISION_PROVIDER': 'openai_compatible', 'AI_VISION_BASE_URL': self.config.base_url,
                   'AI_VISION_MODEL': 'fixture-vision', 'AI_VISION_REVISION': 'fixture-v1'}
            with patch.dict(os.environ, env):
                processor = VisionPageProcessor(freeze('force', ['table_extract']), cache_root=root/'cache', namespace='public:10')
            self.addCleanup(processor.close)
            processor.adapter.session.trust_env = False
            self.server.responses = [(200, reply(TABLE))]
            enhanced = processor.process(parsed, (root/'vision.png').read_bytes())
            self.assertFalse(any(x.startswith('vision_blocking_') for x in enhanced['warnings']))
            page = SimpleNamespace(number=1, height=800, width=600, blocks=enhanced['blocks'])
            chunks = make_chunks([page], self.tokenizer)
            text = '\n'.join(c['text'] for c in chunks)
            self.assertIn('Original reliable tea report body remains searchable.', text)
            self.assertIn('| Iran | 83000 | 115808 |', text)
            self.assertIn('2013 estimated', text)
            self.assertIn('2023 projected', text)
            self.assertIn('Unit: tonnes', text)
            self.assertIn('vision_table_extract', {m['method'] for c in chunks for m in c['metadata']['mappings']})
            self.assert_mappings(chunks, enhanced['blocks'])

    def assert_mappings(self, chunks, blocks):
        lookup = {b['id']: b for b in blocks}
        for chunk in chunks:
            self.assertLessEqual(len(self.tokenizer.encode(chunk['text'], add_special_tokens=False).ids), 800)
            for mapping in chunk['metadata']['mappings']:
                source = lookup[mapping['block_id']]['text'][mapping['block_start']:mapping['block_end']]
                self.assertEqual(source, chunk['text'][mapping['chunk_start']:mapping['chunk_end']])

    def test_long_table_repeats_header_without_splitting_rows(self):
        table = dict(TABLE['tables'][0], rows=[['国家😀' + str(i), str(83000 + i), str(115808 + i)] for i in range(40)])
        text, structure = table_text(table)
        block = {'id': 'p1-v1', 'text': text, 'table': structure, 'kind': 'table', 'bbox': [0, 0, 600, 800],
                 'method': 'vision_table_extract', 'confidence': None, 'heading': False}
        page = SimpleNamespace(number=1, width=600, height=800, blocks=[block])
        chunks = make_chunks([page], self.tokenizer, target=100, maximum=150)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(c['text'].startswith(structure['header']) for c in chunks))
        joined = '\n'.join(c['text'] for c in chunks)
        for row in structure['rows']:
            self.assertEqual(joined.count(row), 1)
        self.assert_mappings(chunks, [block])

    def test_oversized_table_row_rejected(self):
        text, structure = table_text(dict(TABLE['tables'][0], rows=[['x ' * 1000, '1', '2']]))
        block = {'id': 'p1-v1', 'text': text, 'table': structure, 'kind': 'table', 'bbox': [0, 0, 600, 800],
                 'method': 'vision_table_extract', 'confidence': None, 'heading': False}
        with self.assertRaisesRegex(ValueError, 'VISION_TABLE_ROW_TOO_LARGE'):
            make_chunks([SimpleNamespace(number=1, width=600, height=800, blocks=[block])], self.tokenizer)

    def test_disabled_parse_keeps_original_protocol_shape(self):
        import fitz
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)/'native.pdf'
            with fitz.open() as doc:
                doc.new_page().insert_text((60, 60), 'Native extraction remains enabled without vision credentials.')
                doc.save(source)
            cfg = {'max_pages': 200, 'dpi': 200, 'max_pixels': 24000000, 'ocr_timeout': 45,
                   'languages': 'eng', 'min_confidence': 70, 'ocr_mode': 'auto'}
            with redirect_stdout(io.StringIO()):
                result = parser.parse(str(source), 1, str(Path(folder)/'preview.png'), cfg)
            self.assertNotIn('vision_candidates', result)
            self.assertEqual(result['method'], 'native')


class WorkerVisionBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
        import django
        django.setup()

    def test_parser_subprocess_does_not_receive_vision_secret(self):
        from ai_storage.pdf_pipeline import service
        job = SimpleNamespace(pk=uuid.uuid4(), config={})
        with patch.dict(os.environ, {'AI_VISION_API_KEY': 'private-fixture'}), \
                patch.object(service, '_parse_process', return_value={}) as execute:
            service._parse(job, 1, 'preview.png')
        self.assertNotIn('AI_VISION_API_KEY', execute.call_args.args[3])

    def test_cli_default_off_and_explicit_task(self):
        from ai_storage.management.commands.knowledge_pdf import Command
        parser = Command().create_parser('manage.py', 'knowledge_pdf')
        args = ['submit', 'sample.pdf', '--actor-id', '1', '--title', 'Sample', '--source-key', 'sample']
        self.assertEqual(parser.parse_args(args).vision_mode, 'off')
        parsed = parser.parse_args(args + ['--vision-mode', 'force', '--vision-task', 'table_extract'])
        self.assertEqual(parsed.vision_task, ['table_extract'])

    def test_pipeline_config_off_does_not_consume_visual_credentials(self):
        from ai_storage.pdf_pipeline import service
        with tempfile.TemporaryDirectory() as folder:
            token = Path(folder)/'tokenizer.json'
            token.write_text('{}')
            with patch.object(service, 'tokenizer_path', return_value=token), \
                    patch.dict(os.environ, {'AI_VISION_API_KEY': ''}):
                value = service.pipeline_config('eng', 'auto')
            self.assertEqual(value['vision'], {'mode': 'off'})
