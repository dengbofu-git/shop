"""Application MCP stdio client. All Agent data crosses the protocol; no DB fallback."""
import json
import os
import queue
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from dataclasses import asdict
from pathlib import Path

from django.conf import settings

from .cost_control import current_budget, RequestBudget
from .mcp_contracts import ARGUMENTS
from .mcp_security import GRANT_ENV, issue_grant, read_private, write_private
from .pii import redact
from .query_rewrite import QueryPolicy
from .telemetry import agent_span
from .mcp_results import validate_data

MAX_FRAME = 2097152
STATUSES = {'success', 'no_match', 'needs_clarification', 'error'}


class McpServiceError(RuntimeError):
    def __init__(self, code, retryable=False):
        super().__init__('MCP data service: ' + code)
        self.code, self.retryable = code, retryable


class StdioMcpTransport:
    """One initialized protocol session; a bounded reader also works on Windows."""
    def __init__(self, environment):
        root = Path(settings.BASE_DIR)
        executable = Path(settings.SUPPORT_MCP_PYTHON)
        if not executable.is_absolute() or not executable.is_file():
            raise McpServiceError('BACKEND_NOT_CONFIGURED')
        self.process = subprocess.Popen(
            [str(executable), '-u', str(root / 'tools/tea_saas_mcp/server.py')],
            cwd=str(root), env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, start_new_session=os.name != 'nt',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0)
        self.messages = queue.Queue(maxsize=64)
        self.next_id = 0
        self.closed = False
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()
        try:
            result = self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {},
                                  'clientInfo': {'name':'tea-saas-support', 'version':'1.0'}})
            if result.get('protocolVersion') not in ('2024-11-05', '2025-03-26', '2025-06-18'):
                raise McpServiceError('UNSUPPORTED_PROTOCOL')
            self._write({'jsonrpc':'2.0', 'method':'notifications/initialized'})
            self.tools = {tool['name'] for tool in self.request('tools/list', {}).get('tools', [])}
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_FRAME + 1)
                if not line or len(line) > MAX_FRAME or not line.endswith(b'\n'):
                    break
                self.messages.put_nowait(json.loads(line))
        except (ValueError, OSError, queue.Full):
            pass
        finally:
            try:
                self.messages.put_nowait(None)
            except queue.Full:
                pass

    def _write(self, value):
        raw = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8') + b'\n'
        if len(raw) > MAX_FRAME:
            raise McpServiceError('MESSAGE_TOO_LARGE')
        try:
            self.process.stdin.write(raw)
            self.process.stdin.flush()
        except (OSError, ValueError):
            raise McpServiceError('SERVICE_UNAVAILABLE', True) from None

    def request(self, method, params, timeout=None):
        if self.closed:
            raise McpServiceError('SESSION_CLOSED')
        self.next_id += 1
        identity = self.next_id
        self._write({'jsonrpc':'2.0', 'id':identity, 'method':method, 'params':params})
        deadline = time.monotonic() + (timeout or settings.SUPPORT_MCP_CALL_TIMEOUT)
        for _ in range(64):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            try:
                response = self.messages.get(timeout=remaining)
            except queue.Empty:
                break
            if response is None:
                raise McpServiceError('SERVICE_UNAVAILABLE', True)
            if not isinstance(response, dict) or response.get('jsonrpc') != '2.0':
                raise McpServiceError('INVALID_BACKEND_RESPONSE')
            if 'id' not in response:  # Server logging/progress notifications are not results.
                continue
            if type(response['id']) is not int or response['id'] != identity or 'error' in response:
                raise McpServiceError('INVALID_BACKEND_RESPONSE')
            if not isinstance(response.get('result'), dict):
                raise McpServiceError('INVALID_BACKEND_RESPONSE')
            return response['result']
        self.close()
        raise McpServiceError('BACKEND_TIMEOUT', True)

    def close(self):
        if self.closed:
            return
        self.closed = True
        try:
            self.process.stdin.close()
            self.process.wait(timeout=2)
        except (OSError, subprocess.TimeoutExpired):
            if self.process.poll() is None:
                if os.name == 'nt':
                    subprocess.run(['taskkill', '/PID', str(self.process.pid), '/T', '/F'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=5)
                else:
                    os.killpg(self.process.pid, signal.SIGKILL)
            self.process.wait(timeout=5)
        finally:
            self.process.stdout.close()
            self.reader.join(timeout=1)


def validate_payload(tool, payload):
    keys = {'schema_version', 'status', 'data', 'observed_at', 'limitations', 'error_code', 'retryable'}
    if (not isinstance(payload, dict) or set(payload) - keys or payload.get('schema_version') != '1.0'
            or payload.get('status') not in STATUSES or not isinstance(payload.get('limitations'), list)
            or not isinstance(payload.get('observed_at'), str)):
        raise McpServiceError('INVALID_BACKEND_RESPONSE')
    if payload['status'] == 'error':
        code = payload.get('error_code')
        allowed = {'ACCESS_DENIED','INVALID_ARGUMENT','SERVICE_UNAVAILABLE','BACKEND_TIMEOUT',
                   'BACKEND_NOT_CONFIGURED','INVALID_BACKEND_RESPONSE','UNKNOWN_TOOL','CONVERSATION_CONFLICT'}
        if code not in allowed or type(payload.get('retryable')) is not bool:
            raise McpServiceError('INVALID_BACKEND_RESPONSE')
        raise McpServiceError(code, payload['retryable'])
    data = payload.get('data')
    if tool == 'get_product_details' and payload['status'] == 'no_match' and data is None:
        return payload
    if not isinstance(data, dict):
        raise McpServiceError('INVALID_BACKEND_RESPONSE')
    expected = {'get_conversation_context': ('history', list), 'get_saved_preferences': ('memory', (dict, type(None))),
                'validate_categories': ('valid', bool), 'resolve_product': ('sku_id', (int, type(None))),
                'get_product_details': ('sku_id', int), 'search_products': ('recommendations', list),
                'recommend_bundle': ('recommendations', list), 'explain_recommendations': ('explained_products', list),
                'get_order_status': ('orders', list), 'search_knowledge': ('evidence', list)}
    field, kind = expected[tool]
    if field not in data or not isinstance(data[field], kind) or (kind in (bool, int) and type(data[field]) is not kind):
        raise McpServiceError('INVALID_BACKEND_RESPONSE')
    try:
        validate_data(tool, data)
    except (ValueError, TypeError, KeyError):
        raise McpServiceError('INVALID_BACKEND_RESPONSE') from None
    return payload


class AgentDataAccess:
    """Request-owned trusted context; private handoffs never enter tool results."""
    def __init__(self, *, config, message, owner_id=None, conversation=None, references=None,
                 selection=None, order_context=None, preview_history=None):
        self.config, self.order_context = config, order_context
        private_root = Path(settings.SUPPORT_MCP_PRIVATE_ROOT)
        private_root.mkdir(parents=True, exist_ok=True)
        if private_root.is_symlink():
            raise McpServiceError('BACKEND_NOT_CONFIGURED')
        self.folder = tempfile.TemporaryDirectory(prefix='request-', dir=str(private_root.resolve()))
        self.nonce, self.sequence = uuid.uuid4().hex, 0
        self.transport = None
        self.expires = time.time() + min(120, settings.SUPPORT_MCP_REQUEST_TIMEOUT)
        binding = {}
        if preview_history is not None and order_context:
            binding = {key: getattr(order_context, key) for key in ('active_order_id','active_order_at','previous_page')}
            if binding['active_order_at'] is not None:
                binding['active_order_at'] = binding['active_order_at'].isoformat()
        allowed = list(ARGUMENTS)
        if owner_id is None:
            allowed = [x for x in allowed if x not in ('get_saved_preferences','get_order_status')]
        payload = dict(owner_id=owner_id, conversation_id=str(conversation.pk) if conversation else None,
            revision=conversation.revision if conversation else 0, references=references or {},
            message=redact(message), config=asdict(config), selection=selection,
            query_policy=asdict(QueryPolicy.current()),
            preview_history=preview_history or [], mode='preview' if preview_history is not None else 'http',
            order_binding=binding, allowed_tools=allowed, nonce=self.nonce,
            issued_at=time.time(), expires_at=self.expires, private_dir=self.folder.name)
        self.environment = dict(os.environ, TEA_SAAS_PYTHON=sys.executable,
                                **{GRANT_ENV:issue_grant(payload)})
        self.audit, self.last_notes = [], []
        self.remote_usage = {'calls':0, 'input_tokens':0, 'output_tokens':0}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        try:
            if self.transport:
                self.transport.close()
        finally:
            self.transport = None
            self.folder.cleanup()

    def call(self, tool, **arguments):
        if tool not in ARGUMENTS:
            raise McpServiceError('UNKNOWN_TOOL')
        with agent_span('mcp.' + tool, {'agent.mcp.tool':tool}) as span:
            started = time.monotonic()
            try:
                result = self._call(tool, **arguments)
                if span:
                    span.set_attribute('agent.mcp.status', result['status'])
                return result
            except Exception as exc:
                if span:
                    span.set_attribute('agent.mcp.status', 'error')
                    span.set_attribute('error.type', type(exc).__name__)
                raise
            finally:
                if span:
                    span.set_attribute('agent.mcp.duration_ms', (time.monotonic()-started)*1000)

    def _call(self, tool, **arguments):
        if tool not in ARGUMENTS:
            raise McpServiceError('UNKNOWN_TOOL')
        arguments = ARGUMENTS[tool].model_validate(arguments).model_dump(mode='json')
        remaining = self.expires - time.time()
        if remaining <= 0 or self.sequence >= 40:
            raise McpServiceError('BACKEND_TIMEOUT')
        if self.transport is None:
            self.transport = StdioMcpTransport(self.environment)
        if tool not in self.transport.tools:
            raise McpServiceError('UNKNOWN_TOOL')
        budget = current_budget() or RequestBudget()
        allocation = budget.delegate() if tool == 'search_knowledge' else None
        self.sequence += 1
        write_private(self.folder.name, 'input', {'nonce':self.nonce, 'sequence':self.sequence, 'model_budget':allocation})
        usage = None
        handed_off = False
        try:
            reply = self.transport.request('tools/call', {'name':tool, 'arguments':arguments},
                                           timeout=min(settings.SUPPORT_MCP_CALL_TIMEOUT, remaining))
            private = read_private(self.folder.name, 'output', self.nonce, self.sequence)
            handed_off = True
            usage = private.get('model_usage')
            if self.order_context:
                effects = private['order_effects']
                if set(effects) != {'binding_changed','selected_order_id','not_queryable','conversation_missing','navigation_tokens'}:
                    raise McpServiceError('INVALID_BACKEND_RESPONSE')
                for key, value in effects.items():
                    setattr(self.order_context, key, value)
            payload = validate_payload(tool, reply.get('structuredContent'))
            if reply.get('isError'):
                raise McpServiceError('INVALID_BACKEND_RESPONSE')
            if tool == 'search_knowledge':
                self.audit, self.last_notes = payload['data']['audit'], payload['data']['notes']
            return payload
        except Exception as exc:
            # A broken protocol stream cannot be reused or transparently
            # recreated with a fresh grant and fresh counters.
            if self.transport and (not handed_off or not isinstance(exc, McpServiceError)
                                   or exc.code == 'INVALID_BACKEND_RESPONSE'):
                self.transport.close()
            raise
        finally:
            if allocation is not None:
                budget.settle_delegation(allocation, usage)
                if usage:
                    for key in self.remote_usage:
                        self.remote_usage[key] += usage[key]

    def history(self):
        return self.call('get_conversation_context')['data']['history']

    def preferences(self):
        return self.call('get_saved_preferences')['data']['memory']

    def search(self, query):
        return self.call('search_knowledge', query=query)['data']['evidence']

    def scoped_search(self, query, category, scope):
        return self.call('search_knowledge', query=query, category=category, scope=scope)['data']['evidence']

    def notes(self):
        return self.last_notes
