"""DeepSeek wire contract on the pinned LangChain stack; no external requests."""
import json
from unittest import TestCase

import httpx
from django.test import override_settings
from langchain_core.messages import HumanMessage

from .model_client import configured_model
from .cost_control import model_request


class LangChainCompatibilityTests(TestCase):
    def test_configured_plain_reply_uses_chat_completions_and_stream_usage(self):
        calls = []
        def reply(request):
            calls.append((request.url.path,json.loads(request.content)))
            chunks = [
                {'choices':[{'index':0,'delta':{'role':'assistant','content':'合成回答'},'finish_reason':None}]},
                {'choices':[{'index':0,'delta':{},'finish_reason':'stop'}]},
                {'choices':[],'usage':{'prompt_tokens':8,'completion_tokens':3,'total_tokens':11}},
            ]
            data=''.join('data: '+json.dumps(dict(c,id='compat',object='chat.completion.chunk',model='deepseek-flash'))+'\n\n' for c in chunks)+'data: [DONE]\n\n'
            return httpx.Response(200,headers={'Content-Type':'text/event-stream'},content=data.encode())
        with httpx.Client(transport=httpx.MockTransport(reply)) as http, override_settings(
                SUPPORT_API_KEY='synthetic', SUPPORT_BASE_URL='https://example.invalid/v1', SUPPORT_THINKING='disabled'):
            model=configured_model()
            from openai import OpenAI
            model.client.client=OpenAI(api_key='synthetic',base_url='https://example.invalid/v1',http_client=http).chat.completions
            with model_request() as budget:
                answer=model.invoke([HumanMessage(content='合成测试')])
        self.assertEqual(answer.content,'合成回答')
        self.assertEqual(calls[0][0],'/v1/chat/completions')
        self.assertNotIn('max_completion_tokens',calls[0][1])
        self.assertIn('max_tokens',calls[0][1])
        self.assertEqual(calls[0][1]['stream_options'],{'include_usage':True})
        self.assertEqual(budget.snapshot()['input_tokens'],8)
        self.assertEqual(budget.snapshot()['output_tokens'],3)
