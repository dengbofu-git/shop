from unittest import TestCase
from unittest.mock import patch

from .contracts import RecommendationIntent, validate_recommendation_intent, validate_recommendation_branch
from .semantic_planning import DialogueState, plan_turn
from .test_semantic_planning import PlanModel
from .bundle_recommendations import recommend_bundle
from .budget_combinations import Candidate, search_bundles


class BundleIntentBoundaryTests(TestCase):
    def intent(self, **values):
        return RecommendationIntent(action='SEARCH', required={
            'price_basis': 'total', 'budget_max': '3000', **values})

    def history(self):
        intent = RecommendationIntent(action='SEARCH', required={'categories': ['红茶']}, evidence=[{
            'field': 'required.categories', 'value': '红茶', 'source': 'CONTEXT',
            'source_id': 'turn-90', 'quote': '红茶'}])
        return [{'turn_id': 'turn-90', 'user_text': '推荐一款适合日常饮用的红茶',
                 'assistant_text': '推荐结果', 'dialogue_state': DialogueState(status='completed',
                 task='recommendation', purchase=intent).model_dump()}]

    def payload(self, message, *, action='new_request', required=None, evidence=None):
        return {'action': action, 'standalone_question': message,
                'requests': [{'kind': 'recommendation', 'quote': message}],
                'purchase': {'action': 'SEARCH', 'required': required or {
                    'price_basis': 'total', 'budget_max': '3000', 'currency': 'CNY'},
                    'evidence': evidence if evidence is not None else [
                        {'field': 'required.' + f, 'value': v, 'quote': q, 'source': 'CURRENT'}
                        for f, v, q in [('price_basis','total','总价'),
                                       ('budget_max','3000','3000'), ('currency','CNY','块')]]}}

    def test_actual_package_utterance_reaches_model_and_does_not_inherit_red_tea(self):
        message = '推荐总价在3000块的茶品套餐'
        model = PlanModel(self.payload(message))
        plan, source, _ = plan_turn(model, message, self.history(), None)
        self.assertEqual(source, 'model')
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(plan.purchase.required.categories, [])
        checked = validate_recommendation_branch(plan.purchase, tool='recommend_bundle')
        self.assertEqual(checked.action, 'SEARCH')
        self.assertNotIn('purchase_quantity', checked.missing_fields)

    def test_model_cannot_silently_inherit_history_on_new_request(self):
        message = '推荐总价在3000块的茶品套餐'
        payload = self.payload(message)
        payload['purchase']['required']['categories'] = ['红茶']
        payload['purchase']['evidence'].append({'field': 'required.categories', 'value': '红茶',
            'quote': '红茶', 'source': 'CONTEXT', 'source_id': 'turn-90'})
        with self.assertRaisesRegex(ValueError, 'explicit continuation'):
            plan_turn(PlanModel(payload), message, self.history(), None)

    def test_plain_total_new_request_has_no_implicit_topic(self):
        plan, source, _ = plan_turn(None, '推荐总价3000块的茶叶', self.history(), None)
        self.assertEqual(source, 'rules')
        self.assertEqual(plan.purchase.required.categories, [])

    def test_complete_fixed_quantity_keeps_rule_path(self):
        plan, source, _ = plan_turn(None, '推荐总价3000元的三款红茶每款2件', [], None)
        self.assertEqual(source, 'rules')
        checked = validate_recommendation_branch(plan.purchase, tool='recommend_bundle')
        self.assertEqual(checked.action, 'SEARCH')
        self.assertEqual(checked.required.quantity_policy, 'user_specified')

    def test_total_budget_runs_without_quantity_authorization(self):
        with patch('support_ai.bundle_recommendations.ranked_products') as query, patch(
                'support_ai.bundle_recommendations._candidates', return_value=([],False)):
            result = recommend_bundle(self.intent())
        query.assert_called_once()
        self.assertEqual(result['recommendation_status'], 'NO_MATCH')

    def test_default_automatic_quantities_need_no_additional_authorization(self):
        data = self.intent(quantity_policy='automatic').model_dump()
        data['evidence'] = [{'field':'required.'+f,'value':v,'quote':q,'source':'CURRENT'}
            for f,v,q in [('price_basis','total','总价'),('budget_max','3000','3000')]]
        automatic = validate_recommendation_intent(data, '总价3000元', [], None)
        self.assertEqual(automatic.action, 'SEARCH')
        message = '总价3000元，批量采购'
        intent = self.intent(quantity_policy='automatic')
        intent.evidence = [
            {'field':'required.'+f, 'value':v, 'quote':q, 'source':'CURRENT'}
            for f,v,q in [('price_basis','total','总价'), ('budget_max','3000','3000'),
                          ('quantity_policy','automatic','批量采购')]]
        # 模拟结构化输出经契约解析，保证证据模型类型。
        intent = RecommendationIntent.model_validate(intent.model_dump())
        checked = validate_recommendation_intent(intent, message, [], None)
        self.assertEqual(checked.action, 'SEARCH')

    def test_old_automatic_snapshot_is_rechecked(self):
        checked = validate_recommendation_branch(self.intent(), tool='recommend_bundle')
        self.assertEqual(checked.required.quantity_policy, 'automatic')
        self.assertNotIn('purchase_quantity', checked.missing_fields)

    def test_explicit_multiple_composition_cannot_conflict_with_one(self):
        checked = validate_recommendation_branch(self.intent(composition='multiple',
            quantity_per_product=1, distinct_count=1), tool='recommend_bundle')
        self.assertIn('bundle_constraints', checked.missing_fields)

    def test_legacy_budget_baseline_shows_single_unit_failure(self):
        rows = [Candidate(1, 1, '红茶', 704, 498)]
        result = search_bundles(rows, budget_cents=300000)
        self.assertEqual(result['plans'][0]['quantities'], [1])
        near = search_bundles(rows, budget_cents=300000, prefer_near=True)
        self.assertEqual(near['plans'][0]['quantities'], [426])

    def test_multiple_composition_search_keeps_at_least_two_products(self):
        rows = [Candidate(1, 1, '红茶', 100, 10), Candidate(2, 2, '绿茶', 200, 10)]
        result = search_bundles(rows, budget_cents=1000, quantity=1, minimum_distinct=2)
        self.assertTrue(result['plans'])
        self.assertTrue(all(len(p['sku_ids']) >= 2 for p in result['plans']))

    def test_explicit_history_reference_preserves_confirmed_tea(self):
        message = '按刚才的红茶推荐总价3000块的套餐'
        payload = self.payload(message)
        payload['source_turn_ids'] = ['turn-90']
        payload['purchase']['required']['categories'] = ['红茶']
        payload['purchase']['evidence'].append({'field':'required.categories', 'value':'红茶',
            'source':'CONTEXT', 'source_id':'turn-90', 'quote':'红茶'})
        plan, source, _ = plan_turn(PlanModel(payload), message, self.history(), None)
        self.assertEqual(source, 'model')
        self.assertEqual(plan.purchase.required.categories, ['红茶'])

    def test_negative_automatic_permission_is_rejected(self):
        message = '总价3000元，不允许自动配量'
        intent = self.intent(quantity_policy='automatic').model_dump()
        intent['evidence'] = [{'field':'required.'+f, 'value':v, 'quote':q, 'source':'CURRENT'}
            for f,v,q in [('price_basis','total','总价'), ('budget_max','3000','3000'),
                          ('quantity_policy','automatic','不允许自动配量')]]
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, message, [], None)
        intent['evidence'][-1]['quote'] = '自动配量'
        with self.assertRaises(ValueError):
            validate_recommendation_intent(intent, message, [], None)

    def test_only_explicit_fill_budget_rule_authorizes_automatic_quantity(self):
        plan, _, _ = plan_turn(None, '推荐总价3000元的茶，尽量用满', [], None)
        self.assertEqual(plan.purchase.required.quantity_policy, 'automatic')
        self.assertEqual(validate_recommendation_branch(plan.purchase, tool='recommend_bundle').action, 'SEARCH')

    def test_clarifying_plan_normalizes_default_cap_and_sentinel_evidence(self):
        message = '推荐总价3000块的商品套餐'
        payload = self.payload(message, action='clarify')
        payload.update(needs_clarification=True, clarification_question='每款购买几件，还是允许自动配量？')
        payload['purchase']['required'].update(budget_mode='cap', composition='unspecified', quantity_policy='clarify')
        payload['purchase']['missing_fields'] = ['category','purchase_quantity']
        payload['purchase']['evidence'].extend([
            {'field':'required.'+f, 'value':v, 'source':'CURRENT', 'quote':message}
            for f,v in [('budget_mode','cap'),('composition','unspecified'),('quantity_policy','clarify')]])
        model = PlanModel(payload)
        plan, _, _ = plan_turn(model, message, [], None)
        self.assertEqual(len(model.calls), 1)
        self.assertEqual(plan.purchase.required.budget_max, '3000.00')
        self.assertIsNone(plan.purchase.required.budget_mode)
        self.assertFalse(plan.needs_clarification)
        self.assertEqual(plan.purchase.required.quantity_policy, 'automatic')


    def test_explicit_refusal_is_not_overridden_by_automatic_default(self):
        message='推荐总价3000块的套餐，不要自动配量'
        plan,_,_=plan_turn(PlanModel(self.payload(message)),message,[],None)
        checked=validate_recommendation_branch(plan.purchase,tool='recommend_bundle')
        self.assertEqual(checked.action,'CLARIFY')
        self.assertIn('purchase_quantity',checked.missing_fields)


from django.test import TestCase as DatabaseTestCase
from goods.models import Catalog, SPU, SKU
from users.models import UserProfile
from .workflow import build_graph
from .mcp_testing import create_tool_handlers


class BundleIntentMcpTests(DatabaseTestCase):
    def setUp(self):
        merchant = UserProfile.objects.create(username='bundle-boundary-merchant', user_type='merchant', is_active=True)
        for name, price in [('红茶', '7.04'), ('绿茶', '20.00')]:
            category = Catalog.objects.create(name=name)
            product = SPU.objects.create(name='合成'+name, catalog=category, merchant=merchant)
            SKU.objects.create(spu=product, name='合成规格', price=price, market_price=price,
                               cost_price='1.00', stock=500, is_launched=True)

    def run_graph(self, message, history, semantic):
        def factory(state):
            return create_tool_handlers(None, None, state['safe_message'], state['resolved_question'],
                                        state.get('recent_turns', []), None)
        with patch('support_ai.workflow.plan_turn', return_value=semantic):
            return build_graph(None, tool_factory=factory).invoke({
                'message':message, 'recent_turns':history})['response']

    def test_actual_request_automatically_matches_then_fixed_quantity_modification(self):
        helper = BundleIntentBoundaryTests()
        message = '推荐总价在3000块的茶品套餐'
        history = helper.history()
        semantic = plan_turn(PlanModel(helper.payload(message)), message, history, None)
        response = self.run_graph(message, history, semantic)
        self.assertFalse(response['clarification_required'])
        self.assertTrue(response['recommendation_bundles'])
        self.assertEqual(response['dialogue_state']['status'], 'completed')
        self.assertEqual(response['product_intent']['required']['budget_max'], '3000.00')
        self.assertEqual(response['product_intent']['required']['categories'], [])
        import uuid
        from .context import commit_turn, recent_context
        from .models import SupportConversation
        buyer = UserProfile.objects.create(username='bundle-boundary-buyer', user_type='customer', is_active=True)
        saved = commit_turn(buyer, None, 0, uuid.uuid4(), 'synthetic-boundary', message, response)
        history = recent_context(SupportConversation.objects.get(pk=saved['conversation_id']))
        # 简单件数补充沿用已经确认的总预算，真实协议后端查询隔离SKU。
        message = '每款2件'
        semantic = plan_turn(None, message, history, None)
        result = self.run_graph(message, history, semantic)
        self.assertFalse(result['clarification_required'])
        self.assertEqual(result['tasks'][0]['status'], 'success')
        self.assertTrue(result['recommendation_bundles'])
        for bundle in result['recommendation_bundles']:
            self.assertTrue(all(item['quantity'] == 2 for item in bundle['items']))
            self.assertLessEqual(float(bundle['subtotal']), 3000)

    def test_explicit_batch_permission_survives_planner_and_mcp(self):
        helper = BundleIntentBoundaryTests()
        message = '推荐总价3000块的红茶套餐，批量采购，尽量用满'
        payload = helper.payload(message)
        payload['purchase']['required'].update(categories=['红茶'], quantity_policy='automatic', budget_mode='near')
        payload['purchase']['evidence'].extend([
            {'field':'required.'+field,'value':value,'quote':quote,'source':'CURRENT'}
            for field,value,quote in [('categories','红茶','红茶'),
                                     ('quantity_policy','automatic','批量采购'), ('budget_mode','near','尽量用满')]])
        semantic = plan_turn(PlanModel(payload), message, [], None)
        result = self.run_graph(message, [], semantic)
        self.assertEqual(result['tasks'][0]['status'], 'success')
        self.assertEqual(result['recommendation_bundles'][0]['items'][0]['quantity'], 426)
        self.assertEqual(result['recommendation_bundles'][0]['subtotal'], '2999.04')
