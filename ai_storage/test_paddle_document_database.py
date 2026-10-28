"""State/cancellation tests run only on an explicitly disposable PostgreSQL database."""
import json
import os
from pathlib import Path
import re
import struct
import tempfile
import unittest
from unittest.mock import patch

from ai_storage.test_paddle_document import IDENTITY, KEY, REVISION


@unittest.skipUnless(re.fullmatch(r'paddle_document_test_[0-9a-f]{24}', os.getenv('AI_PADDLEOCR_TEST_DATABASE', '')),
                     'Disposable PostgreSQL required')
class PaddleDocumentDatabaseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
        import django
        django.setup()
        from django.conf import settings
        if settings.DATABASES['ai_storage']['NAME'] != os.environ['AI_PADDLEOCR_TEST_DATABASE']:
            raise RuntimeError('Unsafe database target')

    def setUp(self):
        from django.test import override_settings
        from django.db.backends.mysql.base import DatabaseWrapper
        from ai_storage.pdf_pipeline import service
        self.service = service
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        settings = override_settings(AI_PDF_STORAGE_ROOT=self.root / 'storage')
        settings.enable()
        self.addCleanup(settings.disable)
        for value in [patch.object(DatabaseWrapper, 'get_new_connection', side_effect=AssertionError('MySQL forbidden')),
                      patch.object(service, 'operator', return_value=object()),
                      patch.dict(os.environ, {'AI_PADDLEOCR_BASE_URL': 'http://127.0.0.1:18080',
                          'AI_PADDLEOCR_REVISION': REVISION, 'AI_PADDLEOCR_API_KEY': KEY})]:
            value.start()
            self.addCleanup(value.stop)
        import fitz
        self.source = self.root / 'sample.pdf'
        with fitz.open() as doc:
            doc.new_page(width=300, height=400).insert_text((30, 60), 'Synthetic tea report for document parser tests.')
            doc.save(self.source)

    def enqueue(self):
        return self.service.enqueue(self.source, 1, 'Synthetic report', self._testMethodName,
            visibility='public', languages='eng', document_backend='paddleocr', document_mode='force')

    def process(self, job, *, cancel=False, blocked=False):
        from django.db import connections
        from ai_storage.pdf_pipeline.paddleocr import PaddleOCRDocumentAdapter
        def response(adapter, image):
            self.assertFalse(connections['ai_storage'].in_atomic_block)
            if cancel:
                self.service.action(job.pk, 1, 'cancel')
            width, height = struct.unpack('>II', image[16:24])
            return {'identity': IDENTITY,
                    'warnings': ['document_blocking_output_truncated'] if blocked else [],
                    'raw': {'width': width, 'height': height, 'parsing_res_list': [
                        {'block_label': 'text', 'block_content': 'Extracted tea storage facts stay dry and sealed.',
                         'block_id': 0, 'block_order': 1, 'block_bbox': [0, 0, width, height]}]}}
        def embedding(texts, **kwargs):
            self.assertFalse(connections['ai_storage'].in_atomic_block)
            return [[1.0] + [0.0] * 1023 for text in texts]
        with patch.object(PaddleOCRDocumentAdapter, 'extract', response), \
                patch.object(self.service, 'embed_texts', side_effect=embedding) as embed:
            self.service.process(self.service.claim(job.pk))
            job.refresh_from_db()
            return embed.call_count

    def test_complete_draft_and_retry_reuse(self):
        from ai_storage.models import KnowledgePage, KnowledgeChunk
        job = self.enqueue()
        self.assertGreater(self.process(job), 0)
        self.assertEqual(job.status, 'awaiting_review', job.error_code)
        self.assertEqual(job.document.status, 'draft')
        self.assertTrue(KnowledgeChunk.objects.filter(document_id=job.document_id).exists())
        page = KnowledgePage.objects.get(document_id=job.document_id, number=1)
        self.assertEqual(page.method, 'paddleocr_vl')
        self.assertTrue(any(b.get('schema_version') == 'page-ir-v1' for b in page.blocks))
        self.service.action(job.pk, 1, 'cancel')
        self.service.action(job.pk, 1, 'retry')
        self.assertEqual(self.process(job), 0)
        self.assertEqual(job.status, 'awaiting_review')

    def test_cancellation_discards_late_output(self):
        from ai_storage.models import KnowledgePage, KnowledgeChunk
        job = self.enqueue()
        self.assertEqual(self.process(job, cancel=True), 0)
        self.assertEqual(job.status, 'cancelled')
        self.assertFalse(KnowledgePage.objects.filter(document_id=job.document_id).exists())
        self.assertFalse(KnowledgeChunk.objects.filter(document_id=job.document_id).exists())

    def test_queued_old_parser_version_fails_before_model_and_embedding(self):
        job = self.enqueue()
        job.config = dict(job.config, parser='pdf-blocks-v2')
        job.save(update_fields=['config'])
        self.assertEqual(self.process(job), 0)
        self.assertEqual(job.status, 'failed')
        self.assertIn('DOCUMENT_PIPELINE_CHANGED', job.error_code)

    def test_truncation_blocks_embedding_and_publication(self):
        from ai_storage.models import KnowledgeImportJob
        job = self.enqueue()
        self.assertEqual(self.process(job, blocked=True), 0)
        self.assertEqual(job.status, 'failed')
        self.assertIn('DOCUMENT_REVIEW_REQUIRED', job.error_code)
        KnowledgeImportJob.objects.filter(pk=job.pk).update(status='awaiting_review')
        with self.assertRaisesRegex(ValueError, 'Unresolved visual'):
            self.service.action(job.pk, 1, 'publish', accept_warnings=True)
