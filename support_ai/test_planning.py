from unittest import TestCase
from unittest.mock import Mock

from .execution import ToolResult, execute_plan
from .planning import IntentRequest, TaskPlan, TaskStep, build_plan, explicit_requests, extract_requests, validate_plan


class PlanningTests(TestCase):
    def test_complete_graph_compiles(self):
        from langchain_core.runnables import Runnable, RunnableLambda
        from .workflow import build_graph
        class Model(Runnable):
            def with_structured_output(self, schema):
                return RunnableLambda(lambda value: None)
            def invoke(self, input, config=None, **kwargs):
                return None
        self.assertIsNotNone(build_graph(Model()))

    def plan(self, text):
        return build_plan(explicit_requests(text), 'rules', text)

    def test_explicit_introductions_do_not_inherit_shopping_history(self):
        model = Mock()
        history = [{'intent': 'recommendation', 'assistant_text': '已推荐红茶'}]
        for text in ('介绍绿茶', '介绍一下中东的茶叶详情', '介绍一下各种茶叶', '介绍茶叶'):
            requests, source = extract_requests(model, text, text, history)
            self.assertEqual([r.kind for r in requests], ['question_answering'])
            self.assertEqual(source, 'rules')
        model.with_structured_output.assert_not_called()

    def test_mixed_tasks_and_requested_count(self):
        plan = self.plan('先介绍绿茶，再推荐一款红茶')
        self.assertEqual([s.intent for s in plan.steps], ['question_answering', 'recommendation'])
        self.assertEqual(plan.steps[1].limit, 1)

    def test_negative_requests_are_not_executed(self):
        self.assertEqual([s.intent for s in self.plan('不要推荐商品，只介绍绿茶').steps], ['question_answering'])
        self.assertEqual([s.intent for s in self.plan('不是介绍茶叶，我要买红茶').steps], ['recommendation'])

    def test_quoted_recommendation_is_not_a_new_request(self):
        self.assertEqual([s.intent for s in self.plan('介绍你推荐的商品特点').steps], ['product_details'])

    def test_product_dependency_is_program_owned(self):
        plan = self.plan('推荐一款绿茶，再介绍这款商品的特点')
        self.assertEqual(plan.steps[1].depends_on, ['s1'])
        self.assertEqual(plan.steps[1].product_from, 's1')

    def test_forged_tool_and_cycles_are_rejected(self):
        plan = self.plan('介绍绿茶，推荐红茶')
        plan.steps[0].tool = 'delete_database'
        with self.assertRaises(ValueError):
            validate_plan(plan)
        plan = self.plan('介绍绿茶，推荐红茶')
        plan.steps[0].depends_on = ['s2']
        plan.steps[1].depends_on = ['s1']
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_duplicate_output_ids_are_rejected(self):
        plan = self.plan('介绍绿茶，推荐红茶')
        plan.output_order = ['s1', 's1']
        with self.assertRaises(ValueError):
            validate_plan(plan)

    def test_context_only_continues_a_pending_clarification(self):
        requests, source = extract_requests(Mock(), '绿茶', '推荐绿茶', [
            {'intent': 'recommendation', 'assistant_text': '您想选择哪类茶？'}])
        self.assertEqual(requests[0].kind, 'recommendation')
        self.assertEqual(source, 'context_rule')


class ExecutorTests(TestCase):
    def test_no_match_skips_only_dependent_steps(self):
        plan = build_plan(explicit_requests('推荐一款绿茶，再介绍这款商品特点，介绍白茶'), 'rules', '')
        called = []
        def handler(step, previous):
            called.append(step.tool)
            return ToolResult(step_id=step.id, tool=step.tool,
                              status='no_match' if step.intent == 'recommendation' else 'success')
        values = execute_plan(plan, {s.tool: handler for s in plan.steps})
        self.assertEqual([v.status for v in values], ['no_match', 'skipped', 'success'])
        self.assertNotIn('get_product_details', called)

    def test_dependency_overrides_storage_order_but_preserves_output_order(self):
        plan = TaskPlan(source='rules', output_order=['detail', 'rec'], steps=[
            TaskStep(id='detail', intent='product_details', tool='get_product_details', request='介绍推荐的商品',
                     depends_on=['rec'], product_from='rec'),
            TaskStep(id='rec', intent='recommendation', tool='recommend_products', request='推荐绿茶')])
        called = []
        def handler(step, previous):
            called.append(step.id)
            return ToolResult(step_id=step.id, tool=step.tool, status='success')
        result = execute_plan(plan, {s.tool: handler for s in plan.steps})
        self.assertEqual(called, ['rec', 'detail'])
        self.assertEqual([r.step_id for r in result], ['detail', 'rec'])

    def test_error_does_not_silently_complete_a_task(self):
        plan = build_plan([IntentRequest(kind='recommendation', quote='推荐绿茶')], 'rules', '')
        def broken(step, previous):
            raise RuntimeError('private content must not be returned')
        result = execute_plan(plan, {'recommend_products': broken})[0]
        self.assertEqual(result.status, 'error')
        self.assertNotIn('private content', str(result.model_dump()))

    def test_budget_stops_dispatch(self):
        plan = build_plan([IntentRequest(kind='recommendation', quote='推荐绿茶')], 'rules', '')
        handler = Mock()
        result = execute_plan(plan, {'recommend_products': handler}, budget_seconds=0)
        handler.assert_not_called()
        self.assertEqual(result[0].data['error_type'], 'BudgetExceeded')
