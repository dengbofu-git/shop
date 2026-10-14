from io import StringIO
from unittest import skipUnless

from django.core.management import call_command
from django.db import DatabaseError, connections, router, transaction
from django.test import SimpleTestCase, TestCase

from .models import BuyerMemory, EmbeddingSpace, KnowledgeChunk, KnowledgeDocument
from .router import AiStorageRouter


class RoutingTests(SimpleTestCase):
    def test_memory_and_knowledge_are_routed_to_ai_storage_only(self):
        from users.models import UserProfile
        routes = AiStorageRouter()
        for model in (BuyerMemory, EmbeddingSpace, KnowledgeChunk, KnowledgeDocument):
            self.assertEqual(router.db_for_read(model), 'ai_storage')
            self.assertEqual(router.db_for_write(model), 'ai_storage')
        self.assertFalse(routes.allow_migrate('default', 'ai_storage'))
        self.assertFalse(routes.allow_migrate('ai_storage', 'users'))
        self.assertFalse(routes.allow_relation(BuyerMemory(), UserProfile()))


class MemoryTransferTests(TestCase):
    databases = {'default', 'ai_storage'}

    def test_transfer_is_idempotent_and_preserves_newer_memory_and_mysql_source(self):
        from support_ai.models import SupportPreference
        from users.models import UserProfile
        user = UserProfile.objects.create(username='copy-buyer', password='test', email='copy@test.com', phone='')
        SupportPreference.objects.create(user=user, preferences={'categories': ['红茶']})
        call_command('transfer_support_preferences', stdout=StringIO())
        self.assertEqual(BuyerMemory.objects.get(owner_id=user.pk).preferences['categories'], ['红茶'])
        BuyerMemory.objects.filter(owner_id=user.pk).update(preferences={'categories': ['绿茶']})
        call_command('transfer_support_preferences', stdout=StringIO())
        self.assertEqual(BuyerMemory.objects.get(owner_id=user.pk).preferences['categories'], ['绿茶'])
        self.assertEqual(SupportPreference.objects.get(user=user).preferences['categories'], ['红茶'])


@skipUnless(connections['ai_storage'].vendor == 'postgresql', 'requires real pgvector PostgreSQL')
class VectorStorageTests(TestCase):
    databases = {'ai_storage'}

    def setUp(self):
        self.space = EmbeddingSpace.objects.create(key='technical-test-v1', provider='test', model='synthetic', revision='1', dimensions=3)
        self.other_space = EmbeddingSpace.objects.create(key='technical-test-v2', provider='test', model='synthetic', revision='2', dimensions=3)

    def chunk(self, source_key, vector, **kwargs):
        document = KnowledgeDocument.objects.create(source_key=source_key, title=source_key, **kwargs)
        return KnowledgeChunk.objects.create(document=document, ordinal=0, text=source_key, embedding=vector, embedding_space=self.space)

    def test_vector_search_filters_owner_publication_and_embedding_model(self):
        from .knowledge import search_knowledge
        public = self.chunk('public', [1, 0, 0], status='published', visibility='public')
        own = self.chunk('own', [0.9, 0.1, 0], status='published', visibility='private', owner_id=100)
        self.chunk('other-user', [1, 0, 0], status='published', visibility='private', owner_id=200)
        self.chunk('draft', [1, 0, 0], status='draft', visibility='public')
        self.chunk('withdrawn', [1, 0, 0], status='withdrawn', visibility='public')
        other = KnowledgeDocument.objects.create(source_key='other-model', title='Other model', visibility='public', status='published')
        KnowledgeChunk.objects.create(document=other, ordinal=0, text='other', embedding=[1, 0, 0], embedding_space=self.other_space)
        rows = search_knowledge([1, 0, 0], self.space.key, owner_id=100)
        self.assertEqual([row['chunk_id'] for row in rows], [public.pk, own.pk])
        self.assertAlmostEqual(rows[0]['distance'], 0)
        self.assertEqual([row['chunk_id'] for row in search_knowledge([1, 0, 0], self.space.key, 300)], [public.pk])

    def test_database_rejects_wrong_dimensions_zero_vectors_and_mutating_used_space(self):
        for vector in ([1, 2], [0, 0, 0]):
            with self.subTest(vector=vector):
                with self.assertRaises(DatabaseError), transaction.atomic(using='ai_storage'):
                    self.chunk('invalid-' + str(len(vector)), vector, visibility='public')
        self.chunk('valid', [1, 0, 0], visibility='public')
        with self.assertRaises(DatabaseError), transaction.atomic(using='ai_storage'):
            EmbeddingSpace.objects.filter(pk=self.space.pk).update(dimensions=4)

    def test_search_rejects_invalid_query_vectors_before_matching(self):
        from .knowledge import search_knowledge
        for vector in ([1, 2], [float('nan'), 1, 0], [0, 0, 0]):
            with self.subTest(vector=vector), self.assertRaises(ValueError):
                search_knowledge(vector, self.space.key, owner_id=100)
