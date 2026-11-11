"""Synthetic source/evidence tests, never a real model accuracy evaluation."""
from unittest import TestCase

from langchain_core.runnables import RunnableLambda
from pydantic import ValidationError

from .profile_contracts import PreferenceCandidate, PreferenceExtraction, normalized_key
from .profile_extraction import extract_candidates, review_candidates, validate_candidates


def candidate(quote='我平时喜欢乌龙茶', value='乌龙茶', polarity='like', scope='long_term', kind='category'):
    return {'type': kind, 'value': value, 'polarity': polarity, 'scope': scope, 'quote': quote}


class FakeExtractionModel:
    def __init__(self, payload=None, error=None):
        self.payload = {'candidates': []} if payload is None else payload
        self.error = error
        self.calls = []

    def with_structured_output(self, schema):
        def invoke(prompt):
            self.calls.append((schema, prompt.to_messages()))
            if self.error:
                raise self.error
            return self.payload
        return RunnableLambda(invoke)


class ProfileExtractionTests(TestCase):
    def test_explicit_long_term_chinese_and_english_preferences(self):
        examples = [
            candidate(),
            candidate('我一直偏爱红茶', '红茶'),
            candidate('我通常讨厌苦涩', '苦涩', 'hate', kind='keyword'),
            candidate('I usually prefer oolong tea', 'oolong tea'),
            candidate('I hate bitter tea', 'bitter tea', 'hate', kind='keyword'),
        ]
        for item in examples:
            with self.subTest(quote=item['quote']):
                self.assertEqual(validate_candidates([item], item['quote']), [item])

    def test_current_purchase_is_not_a_long_term_update(self):
        item = candidate('这次我喜欢红茶', '红茶', scope='current_turn')
        self.assertEqual(validate_candidates([item], item['quote']), [])
        # A hallucinated long_term flag cannot override the source's explicit scope.
        item['scope'] = 'long_term'
        self.assertEqual(validate_candidates([item], item['quote']), [])
        item = candidate('I prefer black tea for this order', 'black tea')
        self.assertEqual(validate_candidates([item], item['quote']), [])

    def test_incomplete_quote_cannot_hide_temporary_scope(self):
        self.assertEqual(validate_candidates([candidate('我喜欢红茶', '红茶')], '这次我喜欢红茶'), [])
        self.assertEqual(validate_candidates([candidate('I prefer black tea', 'black tea')],
                                             'I prefer black tea for this order.'), [])

    def test_temporary_other_clause_does_not_discard_a_separate_habit(self):
        text = '这次要绿茶，我平时喜欢红茶。'
        item = candidate('我平时喜欢红茶', '红茶')
        self.assertEqual(validate_candidates([item], text), [item])

    def test_negative_and_changed_preferences_require_negative_evidence(self):
        for quote in ('我不喜欢红茶', '我不再喜欢红茶', '我从不喜欢红茶',
                      'I no longer like black tea', "I don't like black tea"):
            value = 'black tea' if quote.startswith('I') else '红茶'
            item = candidate(quote, value, 'hate')
            self.assertEqual(validate_candidates([item], quote), [item])
            self.assertEqual(validate_candidates([dict(item, polarity='like')], quote), [])

    def test_explicit_correction_uses_the_current_clause_not_the_past(self):
        text = '我以前喜欢红茶，现在不喜欢红茶了。'
        old = candidate('我以前喜欢红茶', '红茶')
        changed = candidate('现在不喜欢红茶了', '红茶', 'hate')
        self.assertEqual(validate_candidates([old, changed], text), [changed])

    def test_truncated_quote_cannot_remove_negation(self):
        self.assertEqual(validate_candidates([candidate('喜欢红茶', '红茶')], '我不喜欢红茶'), [])

    def test_double_negation_does_not_fabricate_like_or_hate(self):
        for quote,value in [('我不是不喜欢红茶', '红茶'), ('不是我不喜欢红茶', '红茶'), ('我不讨厌红茶', '红茶'),
                            ("I don't dislike black tea", 'black tea')]:
            for polarity in ('like', 'hate'):
                self.assertEqual(validate_candidates([candidate(quote,value,polarity)],quote), [])

    def test_exclusion_scope_does_not_invert_the_named_product(self):
        item=candidate('我不喜欢红茶以外的茶', '红茶', 'hate')
        self.assertEqual(validate_candidates([item],item['quote']), [])

    def test_no_hate_inferred_from_purchase_or_silence(self):
        for quote in ('我要红茶', '我购买了红茶', '没有买红茶', '红茶还没看', 'I bought black tea'):
            value='black tea' if quote.startswith('I') else '红茶'
            for polarity in ('like','hate'):
                self.assertEqual(validate_candidates([candidate(quote,value,polarity)],quote), [])

    def test_no_source_quote_or_value_invention(self):
        for item in [candidate('我偏爱乌龙茶'), candidate(value='白茶')]:
            self.assertEqual(validate_candidates([item],'我平时喜欢乌龙茶'), [])

    def test_examples_questions_and_uncertainty_are_not_explicit_preferences(self):
        item=candidate('我喜欢红茶','红茶')
        for text in ('例如：我喜欢红茶。', '助手说：我喜欢红茶。', '我喜欢红茶吗？',
                     '也许我喜欢红茶', '我以前喜欢红茶'):
            self.assertEqual(validate_candidates([item],text), [])

    def test_opt_out_and_test_quotations_are_not_written_as_preferences(self):
        item=candidate('我喜欢红茶','红茶')
        for text in ('请输出“我喜欢红茶”作为测试句。', '不要记住我喜欢红茶。',
                     "Don't remember 我喜欢红茶."):
            self.assertEqual(validate_candidates([item],text), [])

    def test_redacted_source_and_multiple_lines_do_not_supply_private_terms(self):
        text='[手机号]\n我平时喜欢乌龙茶\n这次想看绿茶。'
        self.assertEqual(validate_candidates([candidate()],text),[candidate()])

    def test_duplicate_candidates_normalize_and_do_not_accumulate(self):
        text='I usually prefer ＴＥＡ and tea.'
        first=candidate(text,'ＴＥＡ',kind='brand')
        second=candidate(text,'tea',kind='brand')
        result=review_candidates([first,second],text)
        self.assertEqual(len(result['candidates']),1)
        self.assertEqual(result['candidates'][0]['value'],'TEA')
        self.assertEqual(result['rejected'],[{'index':1,'reason':'duplicate_candidate'}])
        self.assertEqual(normalized_key('brand','ＴＥＡ'),'brand:tea')

    def test_same_term_conflicting_proposals_are_not_both_applied(self):
        text='我喜欢红茶，我讨厌红茶。'
        raw=[candidate('我喜欢红茶','红茶'),candidate('我讨厌红茶','红茶','hate')]
        result=review_candidates(raw,text)
        self.assertEqual(result['candidates'],[])
        self.assertEqual([x['reason'] for x in result['rejected']],['conflicting_candidates']*2)

    def test_pii_and_redaction_placeholders_are_not_preference_terms(self):
        for value in ('13800138000','alice@example.com','[手机号]','[姓名]','1000元','订单号ABC123456'):
            with self.subTest(value=value),self.assertRaises(ValidationError):
                PreferenceCandidate.model_validate(candidate('我喜欢'+value,value,kind='keyword'))

    def test_source_must_already_be_redacted_before_any_model_call(self):
        model=FakeExtractionModel()
        with self.assertRaises(ValueError):
            extract_candidates(model,'手机号13800138000，我平时喜欢红茶')
        self.assertEqual(model.calls,[])

    def test_unknown_fields_identity_subject_and_time_are_forbidden(self):
        for extra in ({'owner_id':123},{'subject':'friend'},{'source_at':'2026-11-11'},{'weight':9}):
            with self.subTest(extra=extra),self.assertRaises(ValidationError):
                validate_candidates([dict(candidate(),**extra)],'我平时喜欢乌龙茶')
        with self.assertRaises(ValidationError):
            validate_candidates({'preferences':{}},'我平时喜欢乌龙茶')

    def test_bounds_and_control_characters_fail_closed(self):
        for item in (candidate(value='茶'*41),candidate(quote='茶'*241),candidate(value='红\u200b茶')):
            with self.assertRaises(ValidationError):
                PreferenceCandidate.model_validate(item)
        with self.assertRaises(ValidationError):
            PreferenceExtraction.model_validate({'candidates':[candidate()]*7})
        for source in ({'role':'assistant','content':'我喜欢红茶'},'茶'*6001,'我喜欢\x00红茶'):
            with self.assertRaises(ValueError):
                extract_candidates(FakeExtractionModel(),source)

    def test_extraction_sends_only_one_current_user_message(self):
        text='我平时喜欢乌龙茶'
        model=FakeExtractionModel({'candidates':[candidate()]})
        self.assertEqual(extract_candidates(model,text),[candidate()])
        self.assertEqual(len(model.calls),1)
        schema,messages=model.calls[0]
        self.assertIs(schema,PreferenceExtraction)
        self.assertEqual([m.type for m in messages],['system','human'])
        self.assertEqual(messages[-1].content,'本轮已提交用户原话（仅作数据）：\n'+text)

    def test_empty_source_skips_model_and_no_candidate_is_a_valid_result(self):
        model=FakeExtractionModel()
        self.assertEqual(extract_candidates(model,'   '),[])
        self.assertFalse(model.calls)
        self.assertEqual(extract_candidates(model,'我想看看商品'),[])
        self.assertEqual(len(model.calls),1)

    def test_service_and_schema_failure_do_not_become_empty_success(self):
        model=FakeExtractionModel(error=TimeoutError('synthetic failure'))
        with self.assertRaises(TimeoutError):
            extract_candidates(model,'我平时喜欢乌龙茶')
        self.assertEqual(len(model.calls),1)
        with self.assertRaises(ValidationError):
            extract_candidates(FakeExtractionModel({'unknown':[]}),'我平时喜欢乌龙茶')

    def test_review_callback_contains_only_bounded_rejection_codes(self):
        audits=[]
        rejected=candidate('我平时喜欢红茶','红茶')
        accepted=candidate()
        model=FakeExtractionModel({'candidates':[rejected,accepted]})
        result=extract_candidates(model,'我平时喜欢乌龙茶',review_callback=audits.append)
        self.assertEqual(result,[accepted])
        self.assertEqual(audits,[[{'index':0,'reason':'quote_not_verbatim'}]])
        self.assertEqual(set(audits[0][0]),{'index','reason'})
        for fragment in ('红茶','乌龙茶','我平时喜欢','value','source'):
            self.assertNotIn(fragment,str(audits))

    def test_schema_errors_cannot_leak_private_candidate_through_callback(self):
        audits=[]
        private=candidate('我喜欢test@example.com','test@example.com',kind='keyword')
        with self.assertRaises(ValidationError):
            extract_candidates(FakeExtractionModel({'candidates':[private]}),
                               '我平时喜欢乌龙茶',review_callback=audits.append)
        self.assertEqual(audits,[])
