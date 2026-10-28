from dataclasses import replace
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings

from ai_storage.knowledge import lexical_terms
from .configuration import AgentConfig
from .query_rewrite import QueryPolicy, insufficiency
from .retrieval import KnowledgeRetriever, RetrievalUnavailable, fuse_rankings, retrieve_knowledge
from .retrieval_cache import cached_embedding


def chunk(pk, text='Black tea manufacturing involves oxidation.', document=None):
    return {'chunk_id': pk, 'document_id': document or str(pk), 'document_version': 1,
            'text': text, 'metadata': {}, 'source_title': 'Tea', 'source_reference': ''}


@override_settings(SUPPORT_RAG_CACHE_ENABLED=False)
class HybridRetrievalTests(SimpleTestCase):
    def setUp(self):
        self.config = AgentConfig('test', 'disabled', False, False, '', 1, rerank_enabled=True,
                                 retrieval_candidates=30, retrieval_top_k=5)

    def run_search(self, question, vectors, keywords, translations=None, reranker=None):
        retriever = KnowledgeRetriever(None, self.config, model_factory=lambda: object())
        with patch('support_ai.retrieval.evidence_key', return_value=None), \
             patch('support_ai.retrieval.hybrid_search_ready', return_value=True), \
             patch('support_ai.retrieval.embed_text', return_value=[1, 0]), \
             patch('support_ai.retrieval.search_knowledge', side_effect=vectors) as vector, \
             patch('support_ai.retrieval.search_knowledge_keywords', side_effect=keywords) as keyword, \
             patch('support_ai.retrieval.translate_queries', return_value=(translations or [], 0)) as translate, \
             patch('support_ai.retrieval.rerank_candidates', side_effect=reranker or (lambda q, rows, c: [dict(r, rerank_score=.9) for r in rows])) as rank:
            results = retriever.search(question)
        return results, retriever, vector, keyword, translate, rank

    def test_adequate_first_pass_never_calls_translation_and_uses_both_channels(self):
        rows = [chunk(1)]
        result, retriever, vector, keyword, translate, rank = self.run_search(
            '红茶工艺', lambda *a, **k: rows, lambda *a, **k: rows)
        self.assertEqual([r['chunk_id'] for r in result], [1])
        translate.assert_not_called()
        self.assertEqual(rank.call_args.args[0], '红茶工艺')
        self.assertLessEqual(sum(q['limit'] for q in retriever.audit[0]['queries']), 30)
        self.assertEqual(retriever.audit[0]['coverage']['missing_subjects'], [])

    def test_missing_subject_causes_only_one_translation_then_preserves_scope(self):
        rows = [chunk(1, 'Saudi Arabia tea drinking customs and hospitality.')]
        result, retriever, vector, keyword, translate, rank = self.run_search(
            '沙特和阿联酋饮茶习惯', lambda *a, **k: rows, lambda *a, **k: rows,
            ['Saudi Arabia UAE tea drinking customs hospitality'])
        self.assertEqual(translate.call_count, 1)
        self.assertEqual(rank.call_count, 1)  # No new candidates means no repeated scoring.
        self.assertIn('uae', retriever.audit[0]['coverage']['missing_subjects'])
        self.assertTrue(retriever.notes())
        self.assertTrue(all(call.args[2] is None for call in vector.call_args_list))

    def test_keyword_route_survives_embedding_outage_without_becoming_cached_success(self):
        rows = [chunk(1)]
        with patch('support_ai.retrieval.cached_embedding', side_effect=TimeoutError):
            result, retriever, *_ = self.run_search('black tea manufacturing', lambda *a, **k: [], lambda *a, **k: rows)
        self.assertEqual(len(result), 1)
        self.assertTrue(any(q['status'] == 'error' for q in retriever.audit[0]['queries']))

    def test_all_routes_failing_is_technical_failure(self):
        with self.assertRaises(RetrievalUnavailable):
            self.run_search('black tea manufacturing', TimeoutError(), TimeoutError())

    def test_empty_keyword_results_do_not_hide_vector_failure(self):
        with self.assertRaises(RetrievalUnavailable):
            self.run_search('black tea manufacturing', TimeoutError(), lambda *a, **k: [])

    def test_recovery_next_request_after_failure(self):
        with self.assertRaises(RetrievalUnavailable):
            self.run_search('black tea manufacturing', TimeoutError(), TimeoutError())
        result, *_ = self.run_search('black tea manufacturing', lambda *a, **k: [chunk(1)], lambda *a, **k: [])
        self.assertEqual(len(result), 1)

    @override_settings(SUPPORT_RAG_RERANK_CANDIDATES=2)
    def test_candidate_cap_keeps_comparison_subject_before_scoring(self):
        rows = [chunk(i) for i in range(1, 9)] + [chunk(9, 'Green tea manufacturing stops oxidation.')]
        result, _, _, _, _, rank = self.run_search('红茶和绿茶工艺', lambda *a, **k: rows, lambda *a, **k: [])
        scored = rank.call_args.args[1]
        self.assertEqual(len(scored), 2)
        self.assertIn(9, [r['chunk_id'] for r in scored])

    def test_single_candidate_can_be_sufficient_but_missing_year_is_not(self):
        rows = [chunk(1)]
        self.assertEqual(insufficiency('black tea manufacturing', rows, self.config, QueryPolicy()), [])
        self.assertIn('year_gap', insufficiency('2026 black tea manufacturing', rows, self.config, QueryPolicy()))

    def test_rrf_does_not_add_raw_incomparable_scores(self):
        a, b = chunk(1), chunk(2)
        values = fuse_rankings([[dict(a, keyword_score=999), b], [b, a]], 20)
        self.assertAlmostEqual(values[0]['rrf_score'], 1/61 + 1/62)

    def test_chinese_bigrams_and_literal_query_tokens(self):
        self.assertIn('红茶', lexical_terms('红茶制造工艺 CTC'))
        self.assertIn('工艺', lexical_terms('红茶制造工艺 CTC'))
        self.assertIn('ctc', lexical_terms('红茶制造工艺 CTC'))
        self.assertNotIn('|', lexical_terms("' | ! DROP TABLE"))

    def test_later_cannot_be_expanded_to_after_meal_even_if_reviewer_approves(self):
        from .grounding import generate_grounded_answer
        from .test_grounding import ScriptedModel, claim
        text = 'Coffee is served first, and tea is offered later during hospitality.'
        source = dict(chunk(1, text), source_title='Customs')
        bad = claim(text='沙特待客时先上咖啡，餐后才上茶。', quote=text)
        data, _ = generate_grounded_answer(ScriptedModel(drafts=[[bad]]), '沙特饮茶习惯', [source])
        self.assertEqual(data['grounding']['status'], 'insufficient')
        good_text = 'Tea is offered after dinner during hospitality.'
        good = claim(text='待客时会在晚餐后提供茶。', quote=good_text)
        data, _ = generate_grounded_answer(ScriptedModel(drafts=[[good]]), '饮茶习惯', [dict(source, text=good_text)])
        self.assertEqual(data['grounding']['status'], 'verified')

    @override_settings(SUPPORT_RAG_REWRITE_CALLS=9)
    def test_global_rewrite_cap_is_one(self):
        self.assertEqual(QueryPolicy.current().max_model_calls, 1)

    def test_cached_evidence_is_copied_and_has_no_model_calls(self):
        cache.clear()
        from .retrieval_cache import write
        saved = {'remaining_issues': [], 'queries': [], 'missing_subjects': []}
        write('test-evidence', ([chunk(1)], saved))
        with patch('support_ai.retrieval.evidence_key', return_value='test-evidence'), \
             patch('support_ai.retrieval._hybrid_recall') as recall:
            one = KnowledgeRetriever(None, self.config)
            first = one.search('black tea')
            first[0]['text'] = 'mutated'
            two = KnowledgeRetriever(None, self.config)
            self.assertNotEqual(two.search('black tea')[0]['text'], 'mutated')
        recall.assert_not_called()
        self.assertEqual(two.model_calls, 0)
        self.assertEqual(two.audit[-1]['cache_status'], 'hit')

    def test_pending_migration_keeps_vector_path_working(self):
        from .retrieval import _hybrid_recall
        retriever = KnowledgeRetriever(None, self.config)
        audit = {'queries': []}
        with patch('support_ai.retrieval.hybrid_search_ready', return_value=False), \
             patch('support_ai.retrieval._recall_queries', return_value=[[chunk(1)]]) as vector, \
             patch('support_ai.retrieval.search_knowledge_keywords') as keyword:
            result = _hybrid_recall(['tea'], None, 30, retriever, audit, 0)
        keyword.assert_not_called()
        self.assertEqual(vector.call_args.args[2], 30)
        self.assertEqual(result[0][0]['chunk_id'], 1)
        self.assertEqual(audit['hybrid_status'], 'schema_pending')

    @override_settings(SUPPORT_RAG_CACHE_ENABLED=True)
    def test_embedding_cache_model_revision_and_errors(self):
        cache.clear()
        with patch('support_ai.retrieval_cache.settings.AI_OLLAMA_REVISION', 'a'), \
             patch('support_ai.retrieval_cache.settings.AI_EMBEDDING_SPACE_KEY', 'space'):
            from unittest.mock import Mock
            embed = Mock(return_value=[1.0, 0.0])
            cached_embedding('tea', embed, (2, 8))
            cached_embedding('tea', embed, (2, 8))
            self.assertEqual(embed.call_count, 1)
            with override_settings(AI_OLLAMA_REVISION='b'):
                cached_embedding('tea', embed, (2, 8))
            self.assertEqual(embed.call_count, 2)
            embed.side_effect = TimeoutError
            for _ in range(2):
                with self.assertRaises(TimeoutError):
                    cached_embedding('uncached', embed, (2, 8))
            self.assertEqual(embed.call_count, 4)
