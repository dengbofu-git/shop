"""仅使用本机 HTTP 夹具；不调用真实模型或数据库。"""
import base64
import copy
from dataclasses import replace
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch

import requests

from ai_storage.vision.cache import VisionCache
from ai_storage.vision.config import VisionConfig, current_config, freeze, verify_snapshot
from ai_storage.vision.contracts import VisionError, validate_payload
from ai_storage.vision.openai_compatible import OpenAICompatibleVisionAdapter
from ai_storage.vision.pipeline import VisionPageProcessor


PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
OCR = {'schema_version': 'vision-contract-v1', 'confidence': None, 'warnings': [],
       'blocks': [{'text': '原语言茶叶正文 original text', 'bbox': [0, 0, 1, 1]}]}
TABLE = {'schema_version': 'vision-contract-v1', 'confidence': .8, 'warnings': [], 'tables': [{
    'bbox': [0, .2, 1, .8], 'title': 'Consumption', 'unit': 'tonnes',
    'headers': ['Country', '2013 estimated', '2023 projected'],
    'rows': [['Iran', '83000', '115808'], ['Turkey', '228026', '259503']],
    'notes': ['2023 is projected'], 'uncertain_cells': []}]}
FIGURE = {'schema_version': 'vision-contract-v1', 'confidence': .7, 'warnings': [],
          'figures': [{'text': '审批流程：提交 → 审批。', 'bbox': [0, 0, 1, 1]}]}


def reply(payload=OCR, reason='stop'):
    return {'choices': [{'finish_reason': reason, 'message': {'content': json.dumps(payload, ensure_ascii=False)}}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 20, 'total_tokens': 30}}


class Fixture(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        self.server.requests.append((self.path, dict(self.headers), body))
        status, value = self.server.responses.pop(0)
        data = json.dumps(value).encode('utf8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


class VisionHttpFixture:
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def setUp(self):
        self.server.responses = [(200, reply())]
        self.server.requests = []
        self.config = VisionConfig('openai_compatible', 'http://127.0.0.1:{}/v1'.format(self.server.server_port),
                                   'fixture-vision', 'fixture-v1')
        self.key = patch.dict(os.environ, {'AI_VISION_API_KEY': 'fixture-key'})
        self.key.start()
        self.addCleanup(self.key.stop)

    def adapter(self, config=None):
        session = requests.Session()
        session.trust_env = False
        self.addCleanup(session.close)
        return OpenAICompatibleVisionAdapter(config or self.config, session=session)

    def extract(self, config=None, task='ocr_text'):
        return self.adapter(config).extract(image=PNG, task=task, context='page 1')


class VisionHttpTests(VisionHttpFixture, unittest.TestCase):
    def test_real_http_picture_schema_and_independent_auth(self):
        result = self.extract()
        path, headers, body = self.server.requests[0]
        self.assertEqual(path, '/v1/chat/completions')
        self.assertEqual(headers['Authorization'], 'Bearer fixture-key')
        picture = body['messages'][1]['content'][1]['image_url']
        self.assertEqual(base64.b64decode(picture['url'].split(',')[1]), PNG)
        self.assertNotIn('detail', picture)
        self.assertNotIn('thinking', body)
        self.assertEqual(body['response_format'], {'type': 'json_object'})
        self.assertEqual(result['payload'], OCR)
        self.assertEqual(result['usage']['total_tokens'], 30)

    def test_optional_profile_parameters_are_explicit(self):
        config = replace(self.config, output_format='json_schema', token_parameter='max_completion_tokens',
                         thinking='disabled', image_detail='high', temperature=0)
        self.extract(config)
        body = self.server.requests[0][2]
        self.assertEqual(body['max_completion_tokens'], 4096)
        self.assertNotIn('max_tokens', body)
        self.assertEqual(body['thinking'], {'type': 'disabled'})
        self.assertEqual(body['temperature'], 0)
        self.assertEqual(body['response_format']['json_schema']['strict'], True)

    def test_all_three_task_contracts(self):
        for task, value in [('ocr_text', OCR), ('table_extract', TABLE), ('figure_describe', FIGURE)]:
            with self.subTest(task=task):
                self.server.responses = [(200, reply(value))]
                self.assertEqual(self.extract(task=task)['task'], task)

    def test_transient_failure_retries_then_succeeds(self):
        for status in (429, 503):
            with self.subTest(status=status), patch('ai_storage.vision.openai_compatible.time.sleep'):
                self.server.responses = [(status, {}), (200, reply())]
                self.extract()
                self.assertFalse(self.server.responses)

    def test_auth_and_redirect_are_not_retried(self):
        for status, code in [(401, 'VISION_AUTH_FAILED'), (302, 'VISION_HTTP_ERROR')]:
            with self.subTest(status=status):
                self.server.responses = [(status, {'error': 'private provider text'})]
                with self.assertRaisesRegex(VisionError, '^' + code + '$'):
                    self.extract()

    def test_truncated_output_is_not_accepted(self):
        self.server.responses = [(200, reply(reason='length'))]
        with self.assertRaisesRegex(VisionError, 'VISION_OUTPUT_TRUNCATED'):
            self.extract()

    def test_refusal_is_distinct_from_empty_or_valid_output(self):
        value = reply()
        value['choices'][0]['message']['refusal'] = 'cannot extract'
        self.server.responses = [(200, value)]
        with self.assertRaisesRegex(VisionError, 'VISION_REFUSED'):
            self.extract()

    def test_bad_json_and_duplicate_keys_are_rejected(self):
        for text in ('not JSON', '{"blocks":[],"blocks":[]}'):
            value = reply()
            value['choices'][0]['message']['content'] = text
            self.server.responses = [(200, value)]
            with self.assertRaisesRegex(VisionError, 'VISION_INVALID_RESPONSE'):
                self.extract()

    def test_timeout_has_bounded_attempts_and_fixed_error(self):
        session = Mock()
        session.post.side_effect = requests.Timeout('secret URL and private data')
        with patch('ai_storage.vision.openai_compatible.time.sleep'):
            adapter = OpenAICompatibleVisionAdapter(self.config, session=session)
            with self.assertRaisesRegex(VisionError, '^VISION_TIMEOUT$'):
                adapter.extract(image=PNG, task='ocr_text', context='page 1')
        self.assertEqual(session.post.call_count, 2)

    def test_invalid_inputs_do_not_send_http(self):
        for image, task in [(b'PDF', 'ocr_text'), (PNG, 'sql'), (b'x' * 10000001, 'ocr_text')]:
            with self.subTest(task=task), self.assertRaises(VisionError):
                self.adapter().extract(image=image, task=task, context='page 1')
        self.assertEqual(len(self.server.requests), 0)

    def test_response_size_is_bounded(self):
        self.server.responses = [(200, {'padding': 'x' * 2000001})]
        with self.assertRaisesRegex(VisionError, 'VISION_RESPONSE_TOO_LARGE'):
            self.extract()

    def test_truncation_cannot_poison_success_cache(self):
        env = {'AI_VISION_PROVIDER': 'openai_compatible', 'AI_VISION_BASE_URL': self.config.base_url,
               'AI_VISION_MODEL': 'fixture-vision', 'AI_VISION_REVISION': 'fixture-v1'}
        with tempfile.TemporaryDirectory() as folder, patch.dict(os.environ, env):
            processor = VisionPageProcessor(freeze('force'), cache_root=folder, namespace='private:16:10')
            self.addCleanup(processor.close)
            processor.adapter.session.trust_env = False
            page = {'number': 1, 'width': 600, 'height': 800, 'method': 'ocr', 'warnings': [],
                    'blocks': [], 'has_content': True}
            self.server.responses = [(200, reply(reason='length')), (200, reply())]
            with self.assertRaisesRegex(VisionError, 'VISION_OUTPUT_TRUNCATED'):
                processor.process(page, PNG)
            self.assertEqual(list(Path(folder).rglob('*.json')), [])
            self.assertTrue(processor.process(page, PNG)['blocks'])
            self.assertEqual(len(self.server.requests), 2)


class VisionContractsAndCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.config = VisionConfig('openai_compatible', 'https://fixture.invalid/v1', 'fixture', 'v1')
        self.cache = VisionCache(self.temp.name, 'private:16:10', self.config)

    def test_table_width_and_uncertain_coordinates(self):
        invalid = copy.deepcopy(TABLE)
        invalid['tables'][0]['rows'][0].append('extra')
        with self.assertRaisesRegex(VisionError, 'VISION_INVALID_OUTPUT'):
            validate_payload('table_extract', invalid)
        invalid = copy.deepcopy(OCR)
        invalid['blocks'][0]['bbox'] = [1, 0, 0, 1]
        with self.assertRaises(VisionError):
            validate_payload('ocr_text', invalid)

    def test_unknown_fields_nonfinite_and_nonstring_cells_rejected(self):
        samples = [dict(OCR, sql='SELECT'), dict(OCR, confidence=float('nan'))]
        table = copy.deepcopy(TABLE)
        table['tables'][0]['rows'][0][1] = 83000
        for task, value in [('ocr_text', x) for x in samples] + [('table_extract', table)]:
            with self.subTest(task=task), self.assertRaises(VisionError):
                validate_payload(task, value)

    def test_success_cache_round_trip_and_private_permissions(self):
        key = self.cache.identity(PNG, 'ocr_text', 'page 1')
        self.assertIsNone(self.cache.get(key, 'ocr_text'))
        result = {'task': 'ocr_text', 'payload': OCR, 'provider': 'openai_compatible',
                  'model': self.config.model, 'revision': self.config.revision, 'usage': {}}
        self.cache.put(key, result)
        self.assertEqual(self.cache.get(key, 'ocr_text'), result)
        # 并发相同身份的后完成结果不能覆盖先完成结果。
        self.cache.put(key, dict(result, payload=dict(OCR, confidence=.5)))
        self.assertIsNone(self.cache.get(key, 'ocr_text')['payload']['confidence'])

    def test_cache_identity_covers_scope_task_prompt_and_context(self):
        base = self.cache.identity(PNG, 'ocr_text', 'page 1')
        others = [VisionCache(self.temp.name, 'private:17:10', self.config).identity(PNG, 'ocr_text', 'page 1'),
                  self.cache.identity(PNG, 'table_extract', 'page 1'),
                  self.cache.identity(PNG, 'ocr_text', 'page 2'),
                  VisionCache(self.temp.name, 'private:16:10', replace(self.config, prompt_version='v2')).identity(PNG, 'ocr_text', 'page 1')]
        self.assertNotIn(base, others)

    def test_invalid_cache_does_not_silently_become_a_miss(self):
        key = self.cache.identity(PNG, 'ocr_text', 'page 1')
        path = self.cache.path(key)
        path.parent.mkdir(parents=True)
        path.write_text('{}')
        with self.assertRaisesRegex(VisionError, 'VISION_CACHE_INVALID'):
            self.cache.get(key, 'ocr_text')


class VisionConfigurationAndPipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        env = {k: v for k, v in os.environ.items() if not k.startswith('AI_VISION_')}
        env.update(AI_VISION_PROVIDER='openai_compatible', AI_VISION_BASE_URL='https://fixture.invalid/v1',
                   AI_VISION_MODEL='fixture', AI_VISION_API_KEY='private-test-key', AI_VISION_REVISION='v1')
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)

    def processor(self, mode='force', tasks=None):
        processor = VisionPageProcessor(freeze(mode, tasks), cache_root=self.temp.name, namespace='private:16:10')
        self.addCleanup(processor.close)
        return processor

    def page(self):
        return {'number': 1, 'width': 600, 'height': 800, 'method': 'native', 'warnings': [],
                'has_content': True, 'vision_candidates': [],
                'blocks': [{'id': 'p1-b1', 'text': 'original row text', 'bbox': [0, 160, 600, 640],
                            'method': 'native', 'confidence': None, 'heading': False}]}

    def result(self, processor, task, payload):
        return {'task': task, 'payload': payload, 'provider': 'openai_compatible',
                'model': processor.config.model, 'revision': processor.config.revision, 'usage': {}}

    def test_off_mode_needs_no_credentials(self):
        with patch.dict(os.environ, {'AI_VISION_API_KEY': ''}):
            self.assertEqual(freeze(), {'mode': 'off'})
            with self.assertRaises(VisionError):
                freeze('force')

    def test_freeze_excludes_key_and_rejects_config_drift(self):
        snap = freeze('force')
        self.assertNotIn('private-test-key', json.dumps(snap))
        with patch.dict(os.environ, {'AI_VISION_MODEL': 'changed'}):
            with self.assertRaisesRegex(VisionError, 'VISION_CONFIG_CHANGED'):
                verify_snapshot(snap)

    def test_insecure_remote_url_and_credential_url_rejected(self):
        for url in ('http://remote.invalid/v1', 'https://user:secret@remote.invalid/v1', 'http://[', 'https://remote.invalid:bad/v1'):
            with patch.dict(os.environ, {'AI_VISION_BASE_URL': url}), self.assertRaises(VisionError):
                current_config()

    def test_auto_clean_page_and_blank_force_page_do_not_call(self):
        for mode, blank in [('auto', False), ('force', True)]:
            processor = self.processor(mode)
            page = self.page()
            if blank:
                page.update(has_content=False, blocks=[])
            with patch.object(processor.adapter, 'extract') as extract:
                self.assertEqual(processor.process(page, PNG), page)
                extract.assert_not_called()

    def test_ocr_keeps_original_and_cache_avoids_second_call(self):
        processor = self.processor()
        with patch.object(processor.adapter, 'extract', return_value=self.result(processor, 'ocr_text', OCR)) as call:
            result = processor.process(self.page(), PNG)
            again = processor.process(self.page(), PNG)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(processor.hits, 1)
        self.assertFalse(result['blocks'][0]['indexable'])
        self.assertEqual(result['blocks'][1]['text'], OCR['blocks'][0]['text'])
        self.assertEqual(result['blocks'][1]['bbox'], [0, 0, 600, 800])
        self.assertEqual(again, result)

    def test_table_preserves_rows_and_marks_replaced_original(self):
        processor = self.processor(tasks=['table_extract'])
        with patch.object(processor.adapter, 'extract', return_value=self.result(processor, 'table_extract', TABLE)):
            result = processor.process(self.page(), PNG)
        self.assertFalse(result['blocks'][0]['indexable'])
        table = result['blocks'][1]
        self.assertEqual(table['kind'], 'table')
        self.assertIn('| Iran | 83000 | 115808 |', table['text'])
        self.assertNotIn('vision_blocking_partial_table_overlap', result['warnings'])

    def test_partial_overlap_and_uncertain_cells_block(self):
        processor = self.processor(tasks=['table_extract'])
        page = self.page()
        page['blocks'][0]['bbox'] = [0, 0, 600, 800]
        payload = copy.deepcopy(TABLE)
        payload['tables'][0]['uncertain_cells'] = ['r1c2']
        with patch.object(processor.adapter, 'extract', return_value=self.result(processor, 'table_extract', payload)):
            result = processor.process(page, PNG)
        self.assertIn('vision_blocking_partial_table_overlap', result['warnings'])
        self.assertIn('vision_blocking_uncertain_cells', result['warnings'])

    def test_page_and_provider_attempt_budgets(self):
        with patch.dict(os.environ, {'AI_VISION_MAX_PAGES': '1', 'AI_VISION_MAX_CALLS': '1'}):
            processor = self.processor()
        with patch.object(processor.adapter, 'extract', return_value=self.result(processor, 'ocr_text', OCR)):
            processor.process(self.page(), PNG)
            with self.assertRaisesRegex(VisionError, 'VISION_PAGE_BUDGET_EXCEEDED'):
                processor.process(self.page(), PNG)
        processor._admit()
        with self.assertRaisesRegex(VisionError, 'VISION_CALL_BUDGET_EXCEEDED'):
            processor._admit()
