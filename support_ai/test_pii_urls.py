"""Credential-bearing links are not public evidence URLs; synthetic values only."""
from unittest import TestCase
from langchain_core.messages import HumanMessage
from .pii import redact,redact_messages,redact_value

PRIVATE_URLS=[
    'https://example.invalid/tea.pdf?access_token=synthetic-secret',
    'https://example.invalid/tea.pdf?email=alice%40example.com',
    'https://example.invalid/tea.pdf?%61ccess_token=synthetic-secret',
    'https://example.invalid/tea.pdf#access_token=synthetic-secret',
    'https://synthetic-user:synthetic-secret@example.invalid/tea.pdf',
    'https://example.invalid/tea.pdf?q=alice%40example.com',
    'https://example.invalid/tea.pdf?%2561ccess_token=synthetic-secret',
    'https://example.invalid/tea.pdf?token=&token=synthetic-secret',
    'https://example.invalid/tea.pdf#/callback?ACCESS_TOKEN=synthetic-secret',
    'https://example.invalid/tea.pdf?phone=%31%33%38%30%30%31%33%38%30%30%30',
]
PUBLIC_URLS=[
    'https://example.invalid/tea.pdf?lang=zh&page=2',
    'https://example.invalid/tea.pdf#chapter-2',
    'https://example.invalid/tea.pdf?q=%E9%BB%84%E8%8C%B6%E5%96%9C%E6%AC%A2',
    '/v1/support/knowledge/documents/12/content',
    '/buyer_orders.html#support-order=os-'+'a'*64,
]

class PiiUrlTests(TestCase):
    def test_private_urls_do_not_leave_any_credential_or_encoded_contact(self):
        for url in PRIVATE_URLS:
            with self.subTest(url=url):
                safe=redact(url)
                self.assertEqual(safe,'[敏感链接]')
                self.assertEqual(redact(safe),safe)
                self.assertNotIn('example.invalid',safe)

    def test_public_references_and_authorized_application_routes_are_unchanged(self):
        for url in PUBLIC_URLS:
            with self.subTest(url=url):self.assertEqual(redact(url),url)

    def test_http_sse_history_and_model_use_same_link_policy(self):
        from .streaming import frame
        from .conversation_history import history_value
        from .views import _response
        payload={'source_url':PRIVATE_URLS[0],'public_url':PUBLIC_URLS[0]}
        for safe in (str(redact_value(payload)),str(history_value(payload)),
                frame('done',payload).decode(),_response(payload,200).content.decode(),
                redact_messages([HumanMessage(content=PRIVATE_URLS[0])])[0].content):
            with self.subTest(surface=safe):self.assertNotIn('synthetic-secret',safe)

    def test_redacted_link_is_not_offered_as_a_clickable_citation(self):
        import re
        text='资料 ['+'茶文化'+']('+PRIVATE_URLS[0]+')。'
        safe=redact(text)
        self.assertNotIn('https://',safe)
        self.assertNotIn('synthetic-secret',safe)
        self.assertIn('茶文化',safe)

    def test_real_knowledge_source_projection_keeps_title_but_removes_credentials(self):
        from .grounding import claim_sources
        from .views import _response
        import json
        evidence=[{'source_id':'e1','source_title':'公开茶知识',
            'source_reference':PRIVATE_URLS[0],'metadata':{'year':2026}}]
        sources=claim_sources([{'citations':[{'source_id':'e1'}]}],evidence)
        output=json.loads(_response({'knowledge_sources':sources},200).content)
        self.assertEqual(output['knowledge_sources'][0]['title'],'公开茶知识')
        self.assertEqual(output['knowledge_sources'][0]['url'],'[敏感链接]')
        self.assertEqual(evidence[0]['source_reference'],PRIVATE_URLS[0])
