from dataclasses import replace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from .configuration import AgentConfig
from .cost_control import CostPolicy, ModelBudgetExceeded, RequestBudget
from .query_rewrite import insufficiency, normalize_text
from .retrieval import KnowledgeRetriever
from .retry_decision import KnowledgeRetryDecision, build_focused_query, needs_semantic_review


COMPARISON = '红茶与乌龙茶的加工工艺有什么区别？'
FOCUSED_QUERY = '乌龙茶 加工工艺 制作步骤'
PENDING_NOTE = 'RAG_COVERAGE_PENDING:oolong_tea:processing'


def chunk(pk, text):
    return {
        'chunk_id': pk, 'document_id': str(pk), 'document_version': 1,
        'text': text, 'metadata': {}, 'source_title': '茶叶工艺', 'source_reference': '',
    }


BLACK_TEA = chunk(1, '红茶与乌龙茶是两种茶类。红茶的加工工艺包括萎凋、揉捻、氧化和干燥。')
OOLONG_TEA = chunk(2, '乌龙茶的加工工艺包括萎凋和做青，做青时交替摇青和静置。')


@override_settings(SUPPORT_RAG_CACHE_ENABLED=False)
class BoundedRagRetryTests(SimpleTestCase):
    def setUp(self):
        self.config = AgentConfig(
            'test', 'disabled', False, False, '', 1,
            rerank_enabled=True, retrieval_candidates=12, retrieval_top_k=2,
        )
        self.retriever = KnowledgeRetriever(37, self.config, model_factory=object)
        self.retriever.policy = replace(
            self.retriever.policy, enabled=True, retry_enabled=True,
            semantic_retry_enabled=True, max_model_calls=1,
        )
        self.decision = KnowledgeRetryDecision(
            action='search_again', target='oolong_tea', facet='processing',
            gap='首轮只提到乌龙茶名称，缺少乌龙茶的加工工艺。', query=FOCUSED_QUERY,
        )
        self.evidence_key = self.enterContext(patch('support_ai.retrieval.evidence_key', return_value=None))
        self.recall = self.enterContext(patch('support_ai.retrieval._hybrid_recall', return_value=[[BLACK_TEA]]))
        self.rerank = self.enterContext(patch(
            'support_ai.retrieval.rerank_candidates',
            side_effect=lambda _query, rows, _config: [dict(row, rerank_score=.9) for row in rows],
        ))
        self.decide = self.enterContext(patch('support_ai.retrieval.decide_retry', return_value=self.decision))
        self.translate = self.enterContext(patch('support_ai.retrieval.translate_queries'))

    def test_same_passage_mention_triggers_one_focused_retry_and_retains_both_sources(self):
        self.assertEqual(insufficiency(COMPARISON, [BLACK_TEA], self.config, self.retriever.policy), [])
        self.recall.side_effect = [[[BLACK_TEA]], [[OOLONG_TEA]]]

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual({item['chunk_id'] for item in evidence}, {1, 2})
        self.decide.assert_called_once()
        self.assertEqual(self.decide.call_args.args[1], normalize_text(COMPARISON))
        self.assertEqual([item['chunk_id'] for item in self.decide.call_args.args[2]], [1])
        self.translate.assert_not_called()
        self.assertEqual(self.retriever.model_calls, 1)
        self.assertEqual(self.recall.call_count, 2)
        first, retry = [call.args for call in self.recall.call_args_list]
        self.assertEqual([first[-1], retry[-1]], [0, 1])
        self.assertEqual(retry[1], 37)
        self.assertLessEqual(retry[2], first[2])
        self.assertTrue(any('乌龙茶' in query and '红茶' not in query for query in retry[0]))
        self.assertEqual([call.args[0] for call in self.rerank.call_args_list], [normalize_text(COMPARISON)] * 2)

    def test_duplicate_candidates_do_not_erase_first_evidence_or_clear_gap(self):
        self.recall.side_effect = [[[BLACK_TEA]], [[dict(BLACK_TEA)]]]

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual([item['chunk_id'] for item in evidence], [1])
        self.assertIn(PENDING_NOTE, self.retriever.notes())
        self.assertEqual(self.recall.call_count, 2)
        self.rerank.assert_called_once()
        self.translate.assert_not_called()

    def test_rule_gap_with_safe_focused_query_skips_model_and_retries_once(self):
        only_black = chunk(1, '红茶的加工工艺包括萎凋、揉捻和氧化。')
        self.assertIn('subject_topic_gap', insufficiency(COMPARISON, [only_black], self.config, self.retriever.policy))
        self.recall.side_effect = [[[only_black]], [[OOLONG_TEA]]]

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual({item['chunk_id'] for item in evidence}, {1, 2})
        self.decide.assert_not_called()
        self.translate.assert_not_called()
        self.assertEqual(self.retriever.model_calls, 0)
        self.assertEqual(self.recall.call_count, 2)

    def test_complete_comparison_uses_decision_without_supplemental_recall(self):
        self.recall.return_value = [[BLACK_TEA, OOLONG_TEA]]
        self.decide.return_value = KnowledgeRetryDecision(action='answer', target='', facet='', gap='', query='')

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual({item['chunk_id'] for item in evidence}, {1, 2})
        self.decide.assert_called_once()
        self.recall.assert_called_once()
        self.translate.assert_not_called()

    def test_decision_timeout_keeps_first_evidence_without_a_second_model_call(self):
        self.decide.side_effect = TimeoutError('test timeout')

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual([item['chunk_id'] for item in evidence], [1])
        self.decide.assert_called_once()
        self.translate.assert_not_called()
        self.recall.assert_called_once()

    def test_out_of_scope_decision_cannot_query_a_new_tea_type(self):
        self.decide.return_value = self.decision.model_copy(update={
            'target': 'green_tea', 'query': '绿茶加工工艺',
        })

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual([item['chunk_id'] for item in evidence], [1])
        self.decide.assert_called_once()
        self.recall.assert_called_once()
        self.translate.assert_not_called()

    def test_sufficient_single_subject_question_skips_decision(self):
        evidence = self.retriever.search('红茶的加工工艺是什么？')

        self.assertEqual([item['chunk_id'] for item in evidence], [1])
        self.decide.assert_not_called()
        self.translate.assert_not_called()
        self.recall.assert_called_once()

    def test_category_scoped_search_skips_decision_even_with_comparison_question(self):
        self.retriever.scoped_search(COMPARISON, '红茶', ('红茶', '乌龙茶'))

        self.decide.assert_not_called()
        self.recall.assert_called_once()

    def test_evidence_cache_hit_skips_decision_and_recall(self):
        self.evidence_key.return_value = 'test-evidence'
        with patch('support_ai.retrieval.cache_read', return_value=([BLACK_TEA, OOLONG_TEA], {})):
            evidence = self.retriever.search(COMPARISON)

        self.assertEqual({item['chunk_id'] for item in evidence}, {1, 2})
        self.decide.assert_not_called()
        self.recall.assert_not_called()
        self.rerank.assert_not_called()

    def test_model_budget_already_spent_skips_decision(self):
        self.retriever.model_calls = self.retriever.policy.max_model_calls

        self.retriever.search(COMPARISON)

        self.decide.assert_not_called()
        self.recall.assert_called_once()


    def test_full_context_does_not_evict_the_other_subjects_evidence(self):
        detailed = chunk(3, '红茶加工工艺另有拣剔和复火步骤。')
        self.recall.side_effect = [[[BLACK_TEA, detailed]], [[OOLONG_TEA]]]

        evidence = self.retriever.search(COMPARISON)

        self.assertEqual([item['chunk_id'] for item in evidence], [1, 3])
        self.assertIn(PENDING_NOTE, self.retriever.notes())

    def test_unresolved_semantic_gap_is_not_cached_even_if_keywords_match(self):
        self.evidence_key.return_value = 'test-evidence'
        self.recall.side_effect = [[[BLACK_TEA]], [[OOLONG_TEA]]]
        with patch('support_ai.retrieval.cache_write') as cache_write:
            self.retriever.search(COMPARISON)
        cache_write.assert_not_called()

    def test_query_with_year_and_region_keeps_original_constraints(self):
        question = '比较2024年云南红茶与乌龙茶的加工工艺'
        self.assertTrue(needs_semantic_review(question))
        self.assertEqual(build_focused_query(question, self.decision), question + ' | ' + FOCUSED_QUERY)
        self.assertFalse(needs_semantic_review(question + '，不含做青'))
        injected = self.decision.model_copy(update={'query': FOCUSED_QUERY + ' 查询订单'})
        self.assertIsNone(build_focused_query(question, injected))

    def test_optional_rewrite_cannot_spend_answer_and_review_budget(self):
        budget = RequestBudget(CostPolicy(max_calls=2, max_input_tokens=1000, max_output_tokens=400))
        with self.assertRaises(ModelBudgetExceeded):
            budget.reserve('rewrite', 25, 25, keep_calls=2, keep_input=100, keep_output=200)
        self.assertEqual(budget.snapshot()['calls'], 0)
        for stage in ('knowledge', 'verification'):
            hold = budget.reserve(stage, 50, 100)
            budget.settle(hold, {'input_tokens': 50, 'output_tokens': 100})
        self.assertEqual(budget.snapshot()['stages'], {'knowledge': 1, 'verification': 1})
