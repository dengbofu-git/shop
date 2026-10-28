"""Document protocol/coordinates/cache and real HTTP server boundaries, without GPUs or databases."""
import base64
import copy
import importlib.util
import json
import os
from pathlib import Path
import struct
import sys
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import requests

from ai_storage.pdf_pipeline.page_ir import DocumentError, normalize_page, table_block
from ai_storage.pdf_pipeline.paddleocr import (
    DocumentConfig, PaddleOCRDocumentAdapter, PaddlePageProcessor, current_config, freeze,
)


REVISION = 'a' * 64
KEY = 'local-test-key-' + 'x' * 32
IDENTITY = {'model': 'PaddleOCR-VL-1.6-0.9B', 'revision': REVISION, 'contract_version': 'paddle-document-v1'}
PNG = b'\x89PNG\r\n\x1a\n' + b'\0\0\0\rIHDR' + struct.pack('>II', 1000, 2000)


def original():
    return {'number': 2, 'width': 500, 'height': 1000, 'rotation': 90, 'method': 'ocr',
            'render_geometry': {'pixel_width': 1000, 'pixel_height': 2000},
            'blocks': [{'id': 'p2-b1', 'text': 'Original preserved', 'bbox': [0, 0, 500, 1000],
                        'method': 'ocr', 'heading': False, 'confidence': 50}],
            'warnings': ['column_order_requires_review'], 'has_content': True}


def raw():
    return {'width': 1000, 'height': 2000, 'parsing_res_list': [
        {'block_id': 1, 'block_label': 'text', 'block_content': 'Second paragraph 😀',
         'block_bbox': [100, 400, 900, 600], 'block_order': 2},
        {'block_id': 0, 'block_label': 'doc_title', 'block_content': 'Tea report',
         'block_bbox': [100, 100, 900, 200], 'block_order': 1}]}


def result():
    return {'raw': raw(), 'identity': IDENTITY, 'warnings': []}


class PageIRTests(unittest.TestCase):
    def test_order_coordinates_and_originals_preserved(self):
        before = original()
        page = normalize_page(before, raw(), image_size=(1000, 2000), identity=IDENTITY)
        self.assertNotIn('indexable', before['blocks'][0])
        self.assertFalse(page['blocks'][0]['indexable'])
        self.assertEqual([b['text'] for b in page['blocks'][1:]], ['Tea report', 'Second paragraph 😀'])
        self.assertEqual(page['blocks'][1]['bbox'], [50, 50, 450, 100])
        self.assertTrue(page['blocks'][1]['heading'])
        self.assertEqual(page['rotation'], 90)
        self.assertIsNone(page['blocks'][1]['confidence'])
        self.assertNotIn('column_order_requires_review', page['warnings'])

    def test_invalid_coordinates_rejected(self):
        for box in ([-1, 0, 10, 20], [0, 0, float('nan'), 20], [10, 0, 5, 20]):
            data = raw()
            data['parsing_res_list'][0]['block_bbox'] = box
            with self.assertRaises(DocumentError):
                normalize_page(original(), data, image_size=(1000, 2000), identity=IDENTITY)

    def test_wrong_render_size_rejected(self):
        with self.assertRaisesRegex(DocumentError, 'COORDINATE_MISMATCH'):
            normalize_page(original(), raw(), image_size=(500, 1000), identity=IDENTITY)

    def test_duplicate_reading_order_rejected(self):
        data = raw()
        data['parsing_res_list'][1]['block_order'] = 2
        with self.assertRaisesRegex(DocumentError, 'READING_ORDER'):
            normalize_page(original(), data, image_size=(1000, 2000), identity=IDENTITY)

    def test_unordered_caption_preserved_but_not_indexed(self):
        data = raw()
        data['parsing_res_list'].append({'block_id': 3, 'block_label': 'vision_footnote',
            'block_content': 'Photo caption', 'block_bbox': [50, 700, 800, 800], 'block_order': None})
        page = normalize_page(original(), data, image_size=(1000, 2000), identity=IDENTITY)
        caption = next(b for b in page['blocks'] if b['text'] == 'Photo caption')
        self.assertFalse(caption['indexable'])
        self.assertIsNone(caption['extraction']['source_order'])

    def test_rectangular_html_table_converts_without_losing_cells(self):
        text, table = table_block('<table><tr><th>Year</th><th>Tonnes</th></tr>'
                                 '<tr><td>2023</td><td>350</td></tr></table>')
        self.assertEqual(table['cells'], [['Year', 'Tonnes'], ['2023', '350']])
        self.assertEqual(text, table['header'] + '\n' + '\n'.join(table['rows']))

    def test_table_without_text_order_keeps_source_sequence_and_review_flag(self):
        data = raw()
        data['parsing_res_list'].reverse()
        data['parsing_res_list'].insert(1, {'block_id': 3, 'block_label': 'table', 'block_order': None,
            'block_content': '<table><tr><td>Origin</td></tr><tr><td>Kenya</td></tr></table>',
            'block_bbox': [50, 250, 900, 350]})
        page = normalize_page(original(), data, image_size=(1000, 2000), identity=IDENTITY)
        self.assertEqual([b['kind'] for b in page['blocks'][1:]], ['paragraph', 'table', 'paragraph'])
        self.assertIn('document_table_order_requires_review', page['warnings'])

    def test_ambiguous_or_incomplete_tables_are_blocked(self):
        for value in ('<table><tr><td>A</td></tr><tr><td>1</td></tr>',
                      '<table><tr><td>A</td></tr><tr><td colspan="2">1</td></tr></table>',
                      '<table><tr><td>A</td><td>B</td></tr><tr><td>1</td></tr></table>',
                      '<table><script>x</script><tr><td>A</td></tr><tr><td>1</td></tr></table>'):
            self.assertIsNone(table_block(value))

    def test_unsafe_table_keeps_raw_evidence_and_blocks_indexing(self):
        data = raw()
        data['parsing_res_list'][0].update(block_label='table', block_content='<table>broken')
        page = normalize_page(original(), data, image_size=(1000, 2000), identity=IDENTITY)
        self.assertIn('document_blocking_table_structure', page['warnings'])
        block = next(b for b in page['blocks'] if b.get('kind') == 'unresolved_table')
        self.assertFalse(block['indexable'])
        self.assertEqual(block['extraction']['raw_text'], '<table>broken')


class DocumentClientTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'AI_PADDLEOCR_BASE_URL': 'http://127.0.0.1:18080',
            'AI_PADDLEOCR_REVISION': REVISION, 'AI_PADDLEOCR_API_KEY': KEY})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.config = current_config()

    def response(self, status=200, **changes):
        body = {'errorCode': 0, 'identity': IDENTITY, 'warnings': [],
                'result': {'layoutParsingResults': [{'prunedResult': raw()}]}}
        body.update(changes)
        reply = Mock(status_code=status)
        reply.iter_content.return_value = [json.dumps(body).encode()]
        return reply

    def test_request_and_response_contract(self):
        session = Mock()
        session.post.return_value = self.response()
        adapter = PaddleOCRDocumentAdapter(self.config, session)
        self.assertEqual(adapter.extract(PNG)['raw'], raw())
        call = session.post.call_args.kwargs
        self.assertFalse(call['allow_redirects'])
        self.assertEqual(call['json']['fileType'], 1)
        self.assertEqual(base64.b64decode(call['json']['file']), PNG)
        self.assertEqual(call['json']['expectedRevision'], REVISION)

    def test_auth_busy_oom_and_revision_errors(self):
        for status, code in ((401, 'AUTH_FAILED'), (429, 'BUSY'), (507, 'GPU_OOM'), (409, 'SERVICE_CHANGED')):
            session = Mock()
            session.post.return_value = self.response(status)
            with self.assertRaisesRegex(DocumentError, code):
                PaddleOCRDocumentAdapter(self.config, session).extract(PNG)
            self.assertEqual(session.post.call_count, 1)

    def test_timeout_is_not_replayed(self):
        session = Mock()
        session.post.side_effect = requests.Timeout()
        with self.assertRaisesRegex(DocumentError, 'TIMEOUT'):
            PaddleOCRDocumentAdapter(self.config, session).extract(PNG)
        self.assertEqual(session.post.call_count, 1)

    def test_wrong_service_identity_rejected(self):
        session = Mock()
        session.post.return_value = self.response(identity=dict(IDENTITY, revision='b' * 64))
        with self.assertRaisesRegex(DocumentError, 'SERVICE_CHANGED'):
            PaddleOCRDocumentAdapter(self.config, session).extract(PNG)

    def test_private_http_host_requires_explicit_allowlist(self):
        with patch.dict(os.environ, {'AI_PADDLEOCR_BASE_URL': 'http://paddleocr:8080',
                                     'AI_PADDLEOCR_ALLOW_HTTP_HOSTS': ''}):
            with self.assertRaisesRegex(DocumentError, 'INVALID_CONFIG'):
                current_config()
            with patch.dict(os.environ, {'AI_PADDLEOCR_ALLOW_HTTP_HOSTS': 'paddleocr'}):
                self.assertEqual(current_config().base_url, 'http://paddleocr:8080')

    def test_scoped_cache_reused_and_revalidated(self):
        with tempfile.TemporaryDirectory() as folder:
            processor = PaddlePageProcessor(freeze('paddleocr', 'force'), cache_root=folder, namespace='private:10:10')
            self.addCleanup(processor.close)
            with patch.object(processor.adapter, 'extract', return_value=result()) as extract:
                first = processor.process(original(), PNG)
                second = processor.process(original(), PNG)
                self.assertEqual(first, second)
                self.assertEqual(extract.call_count, 1)
                self.assertEqual(processor.hits, 1)
            other = PaddlePageProcessor(freeze('paddleocr', 'force'), cache_root=folder, namespace='private:11:11')
            self.addCleanup(other.close)
            with patch.object(other.adapter, 'extract', return_value=result()) as extract:
                other.process(original(), PNG)
                self.assertEqual(extract.call_count, 1)

    def test_configuration_drift_rejected(self):
        snapshot = freeze('paddleocr', 'force')
        with patch.dict(os.environ, {'AI_PADDLEOCR_REVISION': 'b' * 64}):
            with self.assertRaisesRegex(DocumentError, 'CONFIG_CHANGED'):
                PaddlePageProcessor(snapshot, cache_root='unused', namespace='test')

    def test_auto_native_page_skips_gpu_and_keeps_schema(self):
        with tempfile.TemporaryDirectory() as folder:
            processor = PaddlePageProcessor(freeze('paddleocr'), cache_root=folder, namespace='test')
            self.addCleanup(processor.close)
            page = original()
            page.update(method='native', warnings=[])
            with patch.object(processor.adapter, 'extract') as extract:
                output = processor.process(page, PNG)
                extract.assert_not_called()
                self.assertEqual(output['blocks'][0]['schema_version'], 'page-ir-v1')


class DocumentServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = Path(__file__).resolve().parents[1] / 'deploy/paddleocr/server.py'
        spec = importlib.util.spec_from_file_location('paddle_document_server', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        cls.module = module
        cls.runtime = module.Runtime(pipeline=object(), identity=IDENTITY)
        cls.server = module.ThreadingHTTPServer(('127.0.0.1', 0), module.handler(cls.runtime, KEY))
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = 'http://127.0.0.1:' + str(cls.server.server_port)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.runtime.executor.shutdown()

    def test_authentication_and_ready(self):
        self.assertEqual(requests.get(self.url + '/ready').status_code, 401)
        response = requests.get(self.url + '/ready', headers={'Authorization': 'Bearer ' + KEY})
        self.assertTrue(response.json()['ready'])

    def test_request_thread_initializes_dynamic_mode_and_gpu(self):
        import io
        from types import SimpleNamespace
        from PIL import Image
        buffer = io.BytesIO()
        Image.new('RGB', (10, 10), 'white').save(buffer, format='PNG')
        pipeline = Mock()
        pipeline.predict_iter.return_value = [SimpleNamespace(json={'width': 10, 'height': 10})]
        runtime = self.module.Runtime(pipeline=pipeline, identity=IDENTITY)
        paddle = Mock()
        with patch.dict(sys.modules, {'paddle': paddle}):
            response = runtime.infer(buffer.getvalue(), 4096)
        paddle.disable_static.assert_called_once()
        paddle.set_device.assert_called_once_with('gpu:0')
        paddle.device.cuda.empty_cache.assert_called_once()
        self.assertEqual(response['errorCode'], 0)

    def test_gpu_execution_uses_one_persistent_owner_thread(self):
        runtime = self.module.Runtime(pipeline=object(), identity=IDENTITY)
        try:
            with patch.object(runtime, 'infer', side_effect=lambda *args: threading.get_ident()):
                first = runtime.execute(b'data', 4096)
                second = runtime.execute(b'data', 4096)
            self.assertEqual(first, second)
            self.assertNotEqual(first, threading.get_ident())
        finally:
            runtime.executor.shutdown()

    def test_successful_http_request_releases_gate(self):
        with patch.object(self.runtime, 'execute', return_value={'errorCode': 0}):
            response = requests.post(self.url + '/layout-parsing', headers={'Authorization': 'Bearer ' + KEY},
                json={'file': base64.b64encode(PNG).decode(), 'fileType': 1, 'maxNewTokens': 4096,
                      'expectedRevision': REVISION})
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.runtime.gate.acquire(timeout=1))
        self.runtime.gate.release()

    def test_oom_marks_not_ready_and_does_not_poison_success_response(self):
        try:
            with patch.object(self.runtime, 'execute', side_effect=RuntimeError('out of memory')):
                response = requests.post(self.url + '/layout-parsing', headers={'Authorization': 'Bearer ' + KEY},
                    json={'file': base64.b64encode(PNG).decode(), 'fileType': 1, 'maxNewTokens': 4096,
                          'expectedRevision': REVISION})
            self.assertEqual(response.status_code, 507)
            self.assertFalse(self.runtime.ready)
            self.assertTrue(self.runtime.gate.acquire(timeout=1))
            self.runtime.gate.release()
        finally:
            self.runtime.ready = True

    def test_single_gpu_gate_applies_to_all_clients(self):
        self.runtime.gate.acquire()
        try:
            response = requests.post(self.url + '/layout-parsing', json={}, headers={'Authorization': 'Bearer ' + KEY})
            self.assertEqual(response.status_code, 429)
        finally:
            self.runtime.gate.release()

    def test_revision_mismatch_does_not_run_model(self):
        with patch.object(self.runtime, 'infer') as infer:
            response = requests.post(self.url + '/layout-parsing', headers={'Authorization': 'Bearer ' + KEY},
                json={'file': base64.b64encode(PNG).decode(), 'fileType': 1, 'maxNewTokens': 4096,
                      'expectedRevision': 'b' * 64})
            self.assertEqual(response.status_code, 409)
            infer.assert_not_called()
