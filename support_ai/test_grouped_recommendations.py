import json
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from pydantic import ValidationError

from .context import context_from_turns
from .contracts import Preferences, RecommendationIntent
from .diagnostics import error_diagnostic
from .planning import build_plan, explicit_requests
from .recommendation_options import BASIC_TEA_TYPES, recommendation_options
from .recommendations import match_product_groups, match_products
from .test_task_tools import ToolModel
from .tool_services import create_tool_handlers


QUESTION = '那我希望你能根据不同的茶叶种类给我进行一些商品推荐，并给出理由'


class GroupedContractTests(SimpleTestCase):
    def test_query_and_saved_preference_have_independent_bounds(self):
        intent = RecommendationIntent(action='SEARCH', required={'categories': list(BASIC_TEA_TYPES)})
        self.assertEqual(len(intent.required.categories), 6)
        with self.assertRaises(ValidationError):
            Preferences(categories=list(BASIC_TEA_TYPES))

    def test_complete_request_and_group_options_are_preserved(self):
        plan = build_plan(explicit_requests(QUESTION), 'rules', QUESTION)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].request, QUESTION)
        self.assertEqual(plan.steps[0].recommendation.mode, 'by_category')
        self.assertEqual(plan.steps[0].recommendation.per_category_limit, 1)

    def test_counts_are_distinct_from_flat_limits(self):
        self.assertEqual(recommendation_options('按茶类每类推荐两款').per_category_limit, 2)
        self.assertEqual(recommendation_options('推荐两款绿茶').mode, 'flat')
        self.assertTrue(recommendation_options('每类推荐五款').clarification)
        self.assertTrue(recommendation_options('不同茶类总共推荐两款').clarification)
        self.assertTrue(recommendation_options('推荐五款绿茶').clarification)
        self.assertEqual(recommendation_options('绿茶和红茶分别推荐一款').mode, 'by_category')
        self.assertTrue(recommendation_options('按不同茶类推荐两款').clarification)

    def test_diagnostics_do_not_expose_input_or_exception_contents(self):
        try:
            RecommendationIntent.model_validate({'action': 'private-raw-content'})
        except ValidationError as exc:
            data = error_diagnostic(exc, 'conditions')
        self.assertNotIn('private-raw-content', str(data))
        self.assertEqual(data['fields'][0]['field'], 'action')

    def test_long_newest_group_history_keeps_references_within_budget(self):
        products = [{'name': '绿' * 100, 'product_name': '茶' * 100, 'group_position': i // 2 + 1,
                     'group_category': BASIC_TEA_TYPES[i // 2]} for i in range(12)]
        turn = SimpleNamespace(pk=1, user_text='推荐' * 500, answer='介绍文字' * 1000,
                               intent='recommendation', response={'recommendations': products,
                               'recommendation_groups': [{'position': i + 1, 'category': c} for i, c in enumerate(BASIC_TEA_TYPES)]})
        history = context_from_turns([turn])
        self.assertLessEqual(len(json.dumps(history, ensure_ascii=False)), 6000)
        self.assertEqual(len(history[0]['product_references']), 12)


class GroupedRecommendationTests(TestCase):
    databases = {'default', 'ai_storage'}

    def setUp(self):
        from goods.models import Catalog, SPU, SKU
        self.skus = {}
        for i, category in enumerate(BASIC_TEA_TYPES):
            catalog = Catalog.objects.create(name=category)
            spu = SPU.objects.create(name=category + '测试商品', catalog=catalog)
            self.skus[category] = [SKU.objects.create(name='规格' + str(n), caption='', spu=spu,
                                    price=str(10 + i + n * 10), cost_price='5', market_price='50', stock=10)
                                   for n in range(2)]

    def run_tool(self, message=QUESTION, payload=None, history=None):
        plan = build_plan(explicit_requests(message), 'rules', message)
        handlers = create_tool_handlers(ToolModel(payload), None, message, message, history or [], None, '[]')
        return handlers['recommend_products'](plan.steps[0], {})

    def test_full_question_covers_all_six_types_without_condition_model(self):
        plan = build_plan(explicit_requests(QUESTION), 'rules', QUESTION)
        model = Mock()
        history = [{'turn_id': 't1', 'intent': 'question_answering', 'user_text': '介绍不同茶叶的区别',
                    'assistant_text': '六大茶类包括绿茶、红茶、白茶、乌龙茶、黄茶、黑茶。'}]
        handler = create_tool_handlers(model, None, QUESTION, QUESTION, history, None, '[]')['recommend_products']
        result = handler(plan.steps[0], {})
        model.with_structured_output.assert_not_called()
        self.assertEqual(result.status, 'success')
        self.assertEqual([p['category'] for p in result.data['recommendations']], list(BASIC_TEA_TYPES))
        self.assertEqual(result.data['product_intent']['required']['categories'], [])
        self.assertIn('推荐依据', result.data['answer'])
        self.assertIn('尚无可验证的风味', result.data['answer'])

    def test_per_group_two_and_total_limit(self):
        result = self.run_tool('按不同茶类每类推荐两款，并给出理由')
        self.assertEqual(len(result.data['recommendations']), 12)
        self.assertTrue(all(len(g['recommendations']) == 2 for g in result.data['recommendation_groups']))
        result = self.run_tool('按不同茶类每类推荐三款')
        self.assertEqual(result.status, 'needs_clarification')
        self.assertFalse(result.data['recommendations'])

    def test_explicit_subset_and_budget_and_exclusion_are_retained(self):
        subset = self.run_tool('绿茶和红茶各推荐一款，并给出理由')
        self.assertEqual([p['category'] for p in subset.data['recommendations']], ['绿茶', '红茶'])
        message = '按不同茶类推荐，每盒不超过12元，不要红茶'
        evidence = lambda field, value: {'field': field, 'value': value, 'source': 'CURRENT', 'quote': message}
        payload = {'action': 'SEARCH', 'required': {'price_max': '12', 'currency': 'CNY', 'price_basis': 'unit'},
                   'excluded': {'categories': ['红茶']}, 'evidence': [evidence('required.price_max', '12'),
                       evidence('required.currency', 'CNY'), evidence('required.price_basis', 'unit'),
                       evidence('excluded.categories', '红茶')]}
        result = self.run_tool(message, payload)
        self.assertEqual([p['category'] for p in result.data['recommendations']], ['绿茶', '白茶'])
        self.assertTrue(all(float(p['price']) <= 12 for p in result.data['recommendations']))
        self.assertNotIn('红茶', [g['category'] for g in result.data['recommendation_groups']])

    def test_plain_group_budget_and_exclusion_do_not_require_a_model(self):
        message = '请按不同茶类推荐商品，每盒单价不超过15美元，不要红茶，并给出理由'
        step = build_plan(explicit_requests(message), 'rules', message).steps[0]
        model = Mock()
        result = create_tool_handlers(model, None, message, message, [], None, '[]')['recommend_products'](step, {})
        model.with_structured_output.assert_not_called()
        self.assertEqual(result.status, 'success')
        self.assertEqual(len(result.data['recommendations']), 5)
        self.assertTrue(all(float(p['price']) <= 15 and p['category'] != '红茶' for p in result.data['recommendations']))

    def test_unknown_qualifiers_keep_model_extraction(self):
        from .tool_services import simple_grouped_intent
        for question in ('不同茶类推荐有机认证商品', '不同茶类推荐每盒15元以内', '不同茶类推荐适合失眠的商品'):
            self.assertIsNone(simple_grouped_intent(question, question, [], None))
        self.assertIsNone(simple_grouped_intent('每盒预算15美元，先介绍茶叶，再按茶类推荐', '再按茶类推荐', [], None))

    def test_missing_group_does_not_borrow_products(self):
        from goods.models import SKU
        SKU.objects.filter(pk__in=[p.pk for p in self.skus['红茶']]).update(stock=0)
        data = self.run_tool().data
        self.assertEqual(len(data['recommendations']), 5)
        self.assertEqual(data['recommendation_groups'][1]['status'], 'no_match')
        self.assertIn('红茶：暂无符合条件', '\n'.join(data['unmet_requirements']))

    def test_partial_group_error_keeps_other_results(self):
        def query(intent, limit):
            if intent.required.categories == ['红茶']:
                raise RuntimeError('sensitive exception content')
            return match_products(intent, limit)
        with patch('support_ai.recommendations.match_products', side_effect=query):
            result = self.run_tool()
        self.assertEqual(result.status, 'success')
        self.assertEqual(result.data['recommendation_status'], 'PARTIAL')
        self.assertEqual(len(result.data['recommendations']), 5)
        self.assertNotIn('sensitive exception content', str(result.model_dump()))

    def test_bad_model_conditions_error_without_unfiltered_query(self):
        with patch('support_ai.tool_services.match_products') as query:
            result = self.run_tool('推荐测试品牌绿茶', {'action': 'SEARCH', 'required': {'categories': ['绿茶']}})
        query.assert_not_called()
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.data['recommendation_status'], 'ERROR')
        self.assertFalse(result.data['recommendations'])
        self.assertEqual(result.data['diagnostics'][0]['error_type'], 'ValueError')

    def test_model_schema_failure_errors_and_reports_field(self):
        result = self.run_tool('推荐测试品牌绿茶', {'action': 'SEARCH', 'required': {'categories': ['茶'] * 13}})
        self.assertEqual(result.status, 'error')
        self.assertEqual(result.data['recommendation_status'], 'ERROR')
        self.assertFalse(result.data['recommendations'])
        self.assertEqual(result.data['diagnostics'][0]['fields'][0]['field'], 'required.categories')

    def test_sixth_product_and_second_group_followups_reload_live_rows(self):
        data = self.run_tool().data
        turn = SimpleNamespace(pk=1, user_text=QUESTION, answer=data['answer'], intent='recommendation',
                               response=data, created_at=timezone.now())
        history = context_from_turns([turn])
        self.assertEqual(len(history[0]['product_references']), 6)
        self.assertNotIn('price', str(history[0]['product_references']))
        for question, expected in [('第六款多少钱', '黑茶'), ('第二类的商品多少钱', '红茶')]:
            plan = build_plan(explicit_requests(question), 'rules', question)
            handler = create_tool_handlers(ToolModel(), None, question, question, history, None, '[]')['get_product_details']
            result = handler(plan.steps[0], {})
            self.assertEqual(result.status, 'success')
            self.assertEqual(result.data['category'], expected)
        question = '第十二款多少钱'
        step = build_plan(explicit_requests(question), 'rules', question).steps[0]
        result = create_tool_handlers(ToolModel(), None, question, question, history, None, '[]')['get_product_details'](step, {})
        self.assertEqual(result.status, 'needs_clarification')

    def test_unsupported_taste_is_not_silently_ignored(self):
        result = self.run_tool('不同茶类推荐适合失眠的人喝的商品',
                               {'action': 'CLARIFY', 'missing_fields': ['unsupported_attribute']})
        self.assertEqual(result.status, 'needs_clarification')
        self.assertFalse(result.data['recommendations'])

    def test_group_with_two_products_clarifies_or_uses_explicit_position(self):
        from goods.models import SKU
        data = self.run_tool('按不同茶类每类推荐两款').data
        history = context_from_turns([SimpleNamespace(pk=1, user_text='按不同茶类每类推荐两款',
                    answer=data['answer'], intent='recommendation', response=data)])
        SKU.objects.filter(pk=self.skus['黑茶'][1].pk).update(price='199.00')
        for question, status, price in [('第二类的商品多少钱', 'needs_clarification', None),
                                        ('第二类第一款多少钱', 'success', '11.00'),
                                        ('第十二款多少钱', 'success', '199.00')]:
            step = build_plan(explicit_requests(question), 'rules', question).steps[0]
            result = create_tool_handlers(ToolModel(), None, question, question, history, None, '[]')['get_product_details'](step, {})
            self.assertEqual(result.status, status)
            if price:
                self.assertEqual(result.data['price'], price)
