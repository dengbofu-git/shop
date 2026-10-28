"""显式指定专用临时 PostgreSQL 时才运行；视觉和 Embedding 均为夹具。"""
import copy
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest.mock import patch

from ai_storage.test_vision import TABLE, VisionHttpFixture, reply


@unittest.skipUnless(re.fullmatch(r'vision_adapter_test_[0-9a-f]{24}', os.getenv('AI_VISION_TEST_DATABASE', '')),
                     'Dedicated disposable PostgreSQL database required')
class VisionDatabaseTests(VisionHttpFixture, unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if os.getenv('AI_POSTGRES_NAME') != os.getenv('AI_VISION_TEST_DATABASE'):
            raise RuntimeError('Isolated database identity mismatch')
        os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'tea_saas.settings')
        import django
        django.setup()
        from django.conf import settings
        if settings.DATABASES['ai_storage']['NAME'] != os.environ['AI_VISION_TEST_DATABASE']:
            raise RuntimeError('Unsafe database target')
        VisionHttpFixture.setUpClass.__func__(cls)

    @classmethod
    def tearDownClass(cls):
        from django.db import connections
        connections.close_all()
        VisionHttpFixture.tearDownClass.__func__(cls)

    def setUp(self):
        VisionHttpFixture.setUp(self)
        from django.test import override_settings
        from ai_storage.pdf_pipeline import service
        from ai_storage.models import KnowledgeDocument, KnowledgeImportJob
        self.service = service
        self.documents = KnowledgeDocument
        self.jobs = KnowledgeImportJob
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.overrides = override_settings(AI_PDF_STORAGE_ROOT=self.root/'storage')
        self.overrides.enable()
        self.addCleanup(self.overrides.disable)
        from django.db.backends.mysql.base import DatabaseWrapper
        mysql = patch.object(DatabaseWrapper, 'get_new_connection', side_effect=AssertionError('Business DB forbidden'))
        mysql.start()
        self.addCleanup(mysql.stop)
        authority = patch.object(service, 'operator', return_value=object())
        authority.start()
        self.addCleanup(authority.stop)
        # 身份鉴权不属于本次数据库夹具验证范围；所有来源均为 public 合成样本。
        self.env = patch.dict(os.environ, {'AI_VISION_PROVIDER': 'openai_compatible',
            'AI_VISION_BASE_URL': self.config.base_url, 'AI_VISION_MODEL': 'fixture-vision',
            'AI_VISION_REVISION': 'fixture-v1'})
        self.env.start()
        self.addCleanup(self.env.stop)
        from django.db import connections
        def vectors(texts, **kwargs):
            self.assertFalse(connections['ai_storage'].in_atomic_block)
            return [[1.0] + [0.0] * 1023 for t in texts]
        embedding = patch.object(service, 'embed_texts', side_effect=vectors)
        embedding.start()
        self.addCleanup(embedding.stop)
        self.server.responses = [(200, reply(TABLE))]
        self.source = self.root/'source.pdf'
        import fitz
        with fitz.open() as doc:
            page = doc.new_page(width=600, height=800)
            page.insert_text((50, 80), 'A synthetic tea reference body remains in the source.')
            for x in (50, 250, 400, 550):
                page.draw_line((x, 230), (x, 320))
            for y in (230, 260, 290, 320):
                page.draw_line((50, y), (550, y))
            for y, cells in [(250, ['Country', '2013 estimated', '2023 projected']),
                             (280, ['Iran', '83000', '115808']), (310, ['Turkey', '228026', '259503'])]:
                for x, text in zip((60, 260, 410), cells):
                    page.insert_text((x, y), text)
            doc.save(self.source)

    def enqueue(self, title='Sample'):
        return self.service.enqueue(self.source, 1, title, self._testMethodName, visibility='public',
                                    languages='eng', vision_mode='force', vision_tasks=['table_extract'])

    def process(self, job, cancel=False):
        from django.db import connections
        from ai_storage.vision.openai_compatible import OpenAICompatibleVisionAdapter
        original = OpenAICompatibleVisionAdapter.extract
        def checked(adapter, **kwargs):
            self.assertFalse(connections['ai_storage'].in_atomic_block)
            adapter.session.trust_env = False
            if cancel:
                self.service.action(job.pk, 1, 'cancel')
            return original(adapter, **kwargs)
        claimed = self.service.claim(job.pk)
        with patch.object(OpenAICompatibleVisionAdapter, 'extract', checked):
            self.service.process(claimed)
        job.refresh_from_db()
        return job

    def test_job_publish_new_version_and_cache_reuse(self):
        from ai_storage.models import KnowledgeChunk
        from ai_storage.knowledge import search_knowledge
        from django.conf import settings
        job = self.process(self.enqueue())
        self.assertEqual(job.status, 'awaiting_review', job.error_code)
        self.assertEqual(self.enqueue().pk, job.pk)
        self.assertEqual(search_knowledge([1.0] + [0.0]*1023, settings.AI_EMBEDDING_SPACE_KEY, None), [])
        with self.assertRaisesRegex(ValueError, 'accept-warnings'):
            self.service.action(job.pk, 1, 'publish')
        self.service.action(job.pk, 1, 'publish', True)
        visible = search_knowledge([1.0] + [0.0]*1023, settings.AI_EMBEDDING_SPACE_KEY, None)
        self.assertEqual({r['document_id'] for r in visible}, {str(job.document_id)})
        self.assertTrue(any('83000' in r['text'] for r in visible))
        next_job = self.process(self.enqueue('Sample v2'))
        self.assertEqual(next_job.status, 'awaiting_review', next_job.error_code)
        self.assertEqual(len(self.server.requests), 1)
        current = self.documents.objects.get(pk=next_job.document_id)
        self.assertEqual(current.metadata['vision_summary']['cache_hits'], 1)
        self.service.action(next_job.pk, 1, 'publish', True)
        self.assertEqual(self.documents.objects.get(pk=job.document_id).status, 'withdrawn')
        self.assertEqual(self.documents.objects.get(pk=next_job.document_id).status, 'published')
        rows = KnowledgeChunk.objects.filter(document_id=next_job.document_id)
        self.assertTrue(rows.exists())
        self.assertFalse(rows.filter(embedding__isnull=True).exists())

    def test_uncertain_table_blocks_embedding_publish_and_retry(self):
        from ai_storage.models import KnowledgeChunk
        payload = copy.deepcopy(TABLE)
        payload['tables'][0]['uncertain_cells'] = ['r1c2']
        self.server.responses = [(200, reply(payload))]
        job = self.process(self.enqueue())
        self.assertEqual(job.status, 'failed')
        self.assertIn('VISION_REVIEW_REQUIRED', job.error_code)
        self.assertTrue(job.warnings)
        self.assertEqual(KnowledgeChunk.objects.filter(document_id=job.document_id).count(), 0)
        # 即便状态被错误恢复到待发布，accept-warnings 也不能绕过阻塞项。
        self.jobs.objects.filter(pk=job.pk).update(status='awaiting_review')
        with self.assertRaisesRegex(ValueError, 'Unresolved visual'):
            self.service.action(job.pk, 1, 'publish', True)
        self.jobs.objects.filter(pk=job.pk).update(status='failed')
        self.service.action(job.pk, 1, 'retry')
        self.process(job)
        self.assertEqual(job.status, 'failed')
        self.assertEqual(len(self.server.requests), 1)

    def test_cancellation_during_vision_discards_page_write(self):
        from ai_storage.models import KnowledgePage, KnowledgeChunk
        job = self.process(self.enqueue(), cancel=True)
        self.assertEqual(job.status, 'cancelled')
        self.assertEqual(KnowledgePage.objects.filter(document_id=job.document_id).count(), 0)
        self.assertEqual(KnowledgeChunk.objects.filter(document_id=job.document_id).count(), 0)
        self.assertEqual(self.documents.objects.get(pk=job.document_id).status, 'draft')
