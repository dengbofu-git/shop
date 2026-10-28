from unittest import skipUnless
from unittest.mock import patch

from django.core.cache import cache
from django.db import connections, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TestCase, TransactionTestCase, override_settings

from .knowledge import search_knowledge_keywords
from .models import KnowledgeChunk, KnowledgeDocument, KnowledgeRevision


@skipUnless(connections['ai_storage'].vendor == 'postgresql', 'requires isolated PostgreSQL')
class KeywordSearchTests(TransactionTestCase):
    databases = {'ai_storage'}

    def setUp(self):
        cache.clear()

    def create(self, name, text='CTC manufacturing process.', **scope):
        document = KnowledgeDocument.objects.create(source_key=name, title=name,
            **dict({'status': 'published', 'visibility': 'public'}, **scope))
        return KnowledgeChunk.objects.create(document=document, ordinal=0, text=text,
                                             metadata={'section_path': ['Tea processing']})

    def epoch(self):
        return KnowledgeRevision.objects.get(pk=1).revision

    def test_keyword_acl_before_ranking_including_unembedded_documents(self):
        public = self.create('public')
        own = self.create('own', visibility='private', owner_id=101)
        self.create('foreign', visibility='private', owner_id=202)
        self.create('draft', status='draft')
        self.create('withdrawn', status='withdrawn')
        self.assertEqual({r['chunk_id'] for r in search_knowledge_keywords('CTC', 101)}, {public.pk, own.pk})
        self.assertEqual([r['chunk_id'] for r in search_knowledge_keywords('CTC', None)], [public.pk])
        self.assertEqual([r['chunk_id'] for r in search_knowledge_keywords('CTC', 202) if r['chunk_id'] == own.pk], [])

    def test_chinese_title_section_and_body_index_keep_original_citation(self):
        row = self.create('红茶制造', '随后进行氧化，再进行干燥。')
        row.refresh_from_db()
        self.assertIn('红茶制造', row.search_text)
        self.assertIn('Tea processing', row.search_text)
        self.assertTrue(row.search_vector)
        results = search_knowledge_keywords('红茶工艺', None)
        self.assertEqual(results[0]['text'], '随后进行氧化，再进行干燥。')
        self.assertNotIn('红茶制造', results[0]['text'])

    def test_bulk_sql_updates_rename_withdraw_delete_and_rollback_invalidate(self):
        row = self.create('before')
        previous = self.epoch()
        KnowledgeChunk.objects.filter(pk=row.pk).update(text='Orthodox method.')
        self.assertGreater(self.epoch(), previous)
        self.assertEqual(search_knowledge_keywords('CTC', None), [])
        self.assertEqual(len(search_knowledge_keywords('Orthodox', None)), 1)
        previous = self.epoch()
        KnowledgeDocument.objects.filter(pk=row.document_id).update(title='uniqueheading')
        self.assertGreater(self.epoch(), previous)
        self.assertEqual(len(search_knowledge_keywords('uniqueheading', None)), 1)
        previous = self.epoch()
        try:
            with transaction.atomic(using='ai_storage'):
                KnowledgeDocument.objects.filter(pk=row.document_id).update(status='withdrawn')
                self.assertGreater(self.epoch(), previous)
                self.assertEqual(search_knowledge_keywords('Orthodox', None), [])
                raise ValueError('rollback synthetic write')
        except ValueError:
            pass
        self.assertEqual(self.epoch(), previous)
        KnowledgeDocument.objects.filter(pk=row.document_id).update(status='withdrawn')
        self.assertEqual(search_knowledge_keywords('Orthodox', None), [])
        previous = self.epoch()
        KnowledgeDocument.objects.filter(pk=row.document_id).delete()
        self.assertGreater(self.epoch(), previous)

    def test_malformed_scope_and_tsquery_input_cannot_escape_filters(self):
        self.create('secret', text='CTC secret', visibility='private', owner_id=202)
        for owner in (0, -1, True, '202'):
            with self.subTest(owner=owner), self.assertRaises(ValueError):
                search_knowledge_keywords('secret', owner)
        self.assertEqual(search_knowledge_keywords("CTC | !secret'); DROP TABLE x; --", None), [])

    @override_settings(SUPPORT_RAG_CACHE_ENABLED=True)
    def test_cache_keys_partition_acl_and_change_after_revocation(self):
        from support_ai.configuration import AgentConfig
        from support_ai.query_rewrite import QueryPolicy
        from support_ai.retrieval_cache import evidence_key
        config = AgentConfig('test', 'disabled', False, False, '', 1)
        row = self.create('cache')
        public = evidence_key('CTC', None, config, QueryPolicy())
        self.assertNotEqual(public, evidence_key('CTC', 101, config, QueryPolicy()))
        KnowledgeDocument.objects.filter(pk=row.document_id).update(visibility='private', owner_id=101)
        self.assertNotEqual(public, evidence_key('CTC', None, config, QueryPolicy()))

    @override_settings(SUPPORT_RAG_CACHE_ENABLED=True)
    def test_real_keyword_pipeline_cache_hit_and_immediate_withdrawal(self):
        from support_ai.configuration import AgentConfig
        from support_ai.retrieval import KnowledgeRetriever
        config = AgentConfig('test', 'disabled', False, False, '', 1)
        row = self.create('cached-CTC')
        def retriever():
            return KnowledgeRetriever(None, config, model_factory=lambda: object())
        with patch('support_ai.retrieval.embed_text', return_value=[1., 0.]), \
             patch('support_ai.retrieval.search_knowledge', return_value=[]), \
             patch('support_ai.retrieval.translate_queries', return_value=([], 0)):
            first = retriever()
            self.assertEqual(first.search('CTC')[0]['chunk_id'], row.pk)
            with patch('support_ai.retrieval._hybrid_recall', side_effect=AssertionError('cache should serve')):
                second = retriever()
                self.assertEqual(second.search('CTC')[0]['chunk_id'], row.pk)
                self.assertEqual(second.audit[-1]['cache_status'], 'hit')
            KnowledgeDocument.objects.filter(pk=row.document_id).update(status='withdrawn')
            self.assertEqual(retriever().search('CTC'), [])

    def test_evidence_cache_disabled_inside_uncommitted_transaction(self):
        from support_ai.configuration import AgentConfig
        from support_ai.query_rewrite import QueryPolicy
        from support_ai.retrieval_cache import evidence_key
        with transaction.atomic(using='ai_storage'):
            self.assertIsNone(evidence_key('CTC', None,
                AgentConfig('test', 'disabled', False, False, '', 1), QueryPolicy()))


@skipUnless(connections['ai_storage'].vendor == 'postgresql', 'requires isolated PostgreSQL')
class HybridMigrationTests(TransactionTestCase):
    databases = {'ai_storage'}

    def test_upgrade_backfill_reverse_and_upgrade_again(self):
        connection = connections['ai_storage']
        # This connection is Django's disposable test DB, never the business DB.
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        try:
            MigrationExecutor(connection).migrate([('ai_storage', '0003_pdf_import_pipeline')])
            old = MigrationExecutor(connection).loader.project_state([('ai_storage', '0003_pdf_import_pipeline')]).apps
            document = old.get_model('ai_storage', 'KnowledgeDocument').objects.using('ai_storage').create(
                source_key='migration', title='红茶工艺', visibility='public', status='published')
            old.get_model('ai_storage', 'KnowledgeChunk').objects.using('ai_storage').create(
                document_id=document.pk, ordinal=0, text='CTC manufacturing process.')
            from .knowledge import hybrid_search_ready, search_knowledge
            self.assertFalse(hybrid_search_ready())
            space = old.get_model('ai_storage', 'EmbeddingSpace').objects.using('ai_storage').create(
                key='old-schema', provider='test', model='test', revision='1', dimensions=3)
            old.get_model('ai_storage', 'KnowledgeChunk').objects.using('ai_storage').filter(
                document_id=document.pk).update(embedding=[1., 0., 0.], embedding_space_id=space.pk)
            self.assertEqual(len(search_knowledge([1., 0., 0.], 'old-schema', None)), 1)
            MigrationExecutor(connection).migrate([('ai_storage', '0004_hybrid_search')])
            result = search_knowledge_keywords('红茶', None)
            self.assertEqual(result[0]['text'], 'CTC manufacturing process.')
            MigrationExecutor(connection).migrate([('ai_storage', '0003_pdf_import_pipeline')])
            MigrationExecutor(connection).migrate([('ai_storage', '0004_hybrid_search')])
            self.assertEqual(len(search_knowledge_keywords('CTC', None)), 1)
        finally:
            MigrationExecutor(connection).migrate([('ai_storage', '0004_hybrid_search')])
