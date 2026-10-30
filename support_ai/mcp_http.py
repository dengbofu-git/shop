"""Python 3.9 client for the local resident MCP service; no process spawning."""
from urllib.parse import urlsplit
import re

import requests
from urllib3.exceptions import HTTPError, ReadTimeoutError
from django.conf import settings

from .mcp_security import GRANT_ENV
from .telemetry import agent_span

MAX_FRAME = 2097152


class HttpMcpTransport:
    def __init__(self, environment):
        from .mcp_client import McpServiceError
        self.error = McpServiceError
        self.closed, self.next_id = False, 0
        self.url = settings.SUPPORT_MCP_URL
        parsed = urlsplit(self.url)
        token = settings.SUPPORT_MCP_SERVICE_TOKEN
        if (parsed.scheme != 'http' or parsed.hostname not in ('127.0.0.1','localhost','::1') or
                parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path != '/mcp' or
                not isinstance(token,str) or not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',token)):
            raise self.error('BACKEND_NOT_CONFIGURED')
        self.close_url = self.url[:-len('/mcp')]+'/agent-session'
        self.session = requests.Session()
        self.session.trust_env = False
        self.session.headers.update({'Authorization':'Bearer '+token,
            'X-Tea-Saas-Agent-Grant':environment[GRANT_ENV],
            'Accept':'application/json, text/event-stream'})
        try:
            with agent_span('mcp.initialize'):
                result = self.request('initialize',{'protocolVersion':'2025-06-18','capabilities':{},
                    'clientInfo':{'name':'tea-saas-support','version':'1.0'}})
            if result.get('protocolVersion') not in ('2024-11-05','2025-03-26','2025-06-18'):
                raise self.error('UNSUPPORTED_PROTOCOL')
            self.session.headers['MCP-Protocol-Version'] = result['protocolVersion']
            self._post({'jsonrpc':'2.0','method':'notifications/initialized'},notification=True)
            with agent_span('mcp.tools.list'):
                self.tools = {tool['name'] for tool in self.request('tools/list',{}).get('tools',[])}
        except Exception:
            self.close()
            raise

    def _post(self, payload, timeout=None, notification=False):
        try:
            with self.session.post(self.url,json=payload,timeout=timeout or settings.SUPPORT_MCP_CALL_TIMEOUT,
                                   allow_redirects=False,stream=True) as response:
                if response.status_code == 202 and notification:
                    return {}
                raw = response.raw.read(MAX_FRAME+1,decode_content=True)
                if len(raw)>MAX_FRAME:
                    raise self.error('INVALID_BACKEND_RESPONSE')
                import json
                try:
                    result = json.loads(raw)
                except (ValueError,UnicodeError):
                    raise self.error('INVALID_BACKEND_RESPONSE') from None
                if response.status_code != 200:
                    if response.status_code in (401,403):
                        raise self.error('ACCESS_DENIED')
                    code = result.get('error_code') if isinstance(result,dict) else None
                    if code not in ('BACKEND_BUSY','BACKEND_TIMEOUT','SERVICE_UNAVAILABLE'):
                        code='SERVICE_UNAVAILABLE'
                    raise self.error(code,True)
                return result
        except (requests.Timeout,ReadTimeoutError):
            raise self.error('BACKEND_TIMEOUT',True) from None
        except (requests.RequestException,HTTPError,OSError):
            raise self.error('SERVICE_UNAVAILABLE',True) from None

    def request(self, method, params, timeout=None):
        if self.closed:
            raise self.error('SESSION_CLOSED')
        self.next_id += 1
        result = self._post({'jsonrpc':'2.0','id':self.next_id,'method':method,'params':params},timeout)
        if (not isinstance(result,dict) or result.get('jsonrpc')!='2.0' or
                type(result.get('id')) is not int or result['id']!=self.next_id or
                'error' in result or not isinstance(result.get('result'),dict)):
            raise self.error('INVALID_BACKEND_RESPONSE')
        return result['result']

    def close(self):
        if self.closed:
            return
        self.closed=True
        try:
            response=self.session.delete(self.close_url,timeout=2,allow_redirects=False)
            response.close()
        except requests.RequestException:
            pass  # A lost close is bounded by the server's lease deadline.
        finally:
            self.session.close()
