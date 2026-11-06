"""Verify that only answer claims with a source can clear a semantic gap."""

import json
from types import SimpleNamespace
from unittest.mock import Mock

from django.test import SimpleTestCase
from langchain_core.runnables import RunnableLambda

from .business_grounding import make_answer_block, needs_model_review
from .grounding import COVERAGE_PENDING, INSUFFICIENT, GroundingCoverageReview, KnowledgeDraft
from .planning import TaskStep
from .tool_services import create_tool_handlers


QUESTION = '红茶和乌龙茶的制作工艺有什么区别？'
GAP = f'{COVERAGE_PENDING}:oolong_tea:processing'
LIMITATION = '关于乌龙茶的加工，本次资料不足以核实。'
RED = {'text': '红茶与乌龙茶的加工工艺不同。红茶的工艺包含揉捻和干燥。', 'source_title': '加工资料'}
OOLONG = {'text': '乌龙茶的加工工序包含做青和焙火。', 'source_title': '工艺资料'}


def claim(source, source_id, text):
    return {'text': text, 'citations': [{'source_id': source_id, 'quote': source['text']}]}


class ScriptedModel:
    def __init__(self, drafts, annotate):
        self.drafts = drafts
        self.annotate = annotate
        self.calls = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            payload = json.loads(prompt.to_messages()[-1].content)
            self.calls.append((schema, payload))
            if schema is KnowledgeDraft:
                return {'claims': self.drafts}
            if schema is GroundingCoverageReview:
                return {'verdicts': [dict(claim_id=row['claim_id'], standalone=True, relevant=True,
                                          **self.annotate(row)) for row in payload['claims']]}
            raise AssertionError('Unexpected model stage')
        return RunnableLambda(invoke)


class SemanticCoverageTests(SimpleTestCase):
    def run_question(self, model, evidence, notes):
        access = SimpleNamespace(search=Mock(return_value=evidence), scoped_search=Mock(), notes=lambda: notes)
        handlers = create_tool_handlers(model, None, QUESTION, QUESTION, [], {}, data_access=access)
        step = TaskStep(id='s1', intent='question_answering', tool='introduce_tea', request=QUESTION)
        response = handlers[step.tool](step, {}).model_dump()
        access.search.assert_called_once_with(QUESTION)
        access.scoped_search.assert_not_called()
        return response

    def test_single_sided_claim_stays_partial_even_if_reviewer_misassigns_target(self):
        red_claim = claim(RED, 'e1', '红茶的工艺包含揉捻和干燥。')
        model = ScriptedModel([red_claim], lambda row: {'supported': True, 'covered_targets': ['t1']})
        response = self.run_question(model, [RED], [GAP, f'{COVERAGE_PENDING}:white_tea:processing', GAP])
        data = response['data']
        self.assertEqual(data['grounding']['status'], 'partial')
        self.assertEqual(data['grounding']['rejected_count'], 0)
        self.assertEqual(data['evidence_limitations'], [LIMITATION])
        self.assertEqual(response['unmet_requirements'], [LIMITATION])
        self.assertIn(red_claim['text'], data['answer'])
        self.assertIn(LIMITATION, make_answer_block(response)['text'])
        self.assertNotIn(COVERAGE_PENDING, str(response))
        self.assertFalse(needs_model_review([response]))
        self.assertEqual([schema for schema, _ in model.calls], [KnowledgeDraft, GroundingCoverageReview])

    def test_pending_target_clears_only_after_an_accepted_cited_claim(self):
        red_claim = claim(RED, 'e1', '红茶的工艺包含揉捻和干燥。')
        oolong_claim = claim(OOLONG, 'e2', OOLONG['text'])
        for supported in (False, True):
            with self.subTest(supported=supported):
                def annotate(row):
                    return ({'supported': supported, 'covered_targets': ['t1']} if row['claim_id'] == 'c2'
                            else {'supported': True, 'covered_targets': []})

                model = ScriptedModel([red_claim, oolong_claim], annotate)
                data = self.run_question(model, [RED, OOLONG], [GAP])['data']
                self.assertEqual(data['evidence_limitations'], [] if supported else [LIMITATION])
                self.assertEqual(data['grounding']['status'], 'verified' if supported else 'partial')
                self.assertEqual(OOLONG['text'] in data['answer'], supported)
                self.assertEqual(len(model.calls), 2)

    def test_no_evidence_keeps_fixed_abstention_with_no_model_calls(self):
        model = ScriptedModel([], lambda row: {})
        response = self.run_question(model, [], [GAP])
        self.assertEqual(response['status'], 'no_match')
        self.assertEqual(response['data']['answer'], INSUFFICIENT)
        self.assertEqual(response['unmet_requirements'], [LIMITATION])
        self.assertFalse(needs_model_review([response]))
        self.assertFalse(model.calls)
