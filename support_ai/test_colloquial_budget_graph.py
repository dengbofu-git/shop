"""Exercise real planner/tool boundaries using isolated settings and no database."""
from unittest.mock import patch

from django.test import SimpleTestCase

from .tool_services import create_tool_handlers
from .workflow import build_graph


class ColloquialBudgetGraphTests(SimpleTestCase):
    def graph(self):
        def factory(state):
            return create_tool_handlers(None, None, state['safe_message'], state['resolved_question'],
                state.get('recent_turns', []), None)
        return build_graph(None, tool_factory=factory)

    def first_turn(self):
        return self.graph().invoke({'message': '推荐400块左右的茶'})['response']

    def history(self, response):
        snapshot = response['dialogue_state']
        for evidence in snapshot['purchase']['evidence']:
            evidence.update(source='CONTEXT', source_id='turn-1')
        return [{'turn_id': 'turn-1', 'user_text': '推荐400块左右的茶', 'assistant_text': response['answer'],
                 'dialogue_state': snapshot}]

    def test_real_handler_asks_only_scope_and_saves_the_amount(self):
        response = self.first_turn()
        self.assertEqual(response['answer'], '您说的人民币400，是每件商品的预算，还是整套商品的总预算？')
        self.assertEqual(response['dialogue_state']['status'], 'pending')
        self.assertEqual(response['dialogue_state']['missing_fields'], ['budget_scope'])
        self.assertEqual(response['product_intent']['required']['price_max'], '400.00')
        self.assertEqual(response['diagnostics'], [])

    def test_confirming_total_reaches_bundle_tool_with_preserved_money(self):
        history = self.history(self.first_turn())
        with patch('support_ai.tool_services.recommend_bundle', return_value={
                'recommendation_status': 'NO_MATCH', 'recommendations': [], 'answer': '合成候选为空。'}) as tool:
            response = self.graph().invoke({'message': '总价', 'recent_turns': history})['response']
        tool.assert_called_once()
        required = tool.call_args.args[0].required
        self.assertEqual(required.budget_max, '400.00')
        self.assertEqual(required.budget_mode, 'near')
        self.assertEqual(required.currency, 'CNY')
        self.assertEqual(response['tasks'][0]['tool'], 'recommend_bundle')
        self.assertFalse(response['clarification_required'])

    def test_planning_failure_keeps_content_free_diagnostic(self):
        with patch('support_ai.workflow.plan_turn', side_effect=ValueError('意向条件无法对应输入证据')):
            response = self.graph().invoke({'message': '合成无效条件'})['response']
        self.assertEqual(response['diagnostics'], [{'stage': 'semantic.plan', 'error_type': 'ValueError',
                                                  'fields': [], 'message': '意向条件无法对应输入证据'}])
