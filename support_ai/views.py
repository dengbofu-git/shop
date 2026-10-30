import json
import logging
import hashlib
import uuid
import re
from functools import wraps

from django.conf import settings
from django.db import DatabaseError, InterfaceError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods

from tea_saas.utils import jwt_decode
from users.models import UserProfile
from ai_storage.models import BuyerMemory

from .contracts import Preferences
from .context import (ConversationConflict, PreferenceStorageUnavailable, commit_turn,
                      replay, saved_preferences, HISTORY_TURNS)
from .models import SupportConversation
from .conversation_history import list_conversations, conversation_page
from .order_contracts import prepare_order_input
from .order_queries import OrderQueryContext, attach_order_links
from pydantic import ValidationError
from .mcp_client import AgentDataAccess, McpServiceError
from .planning import explicit_requests
from .streaming import progress, StreamCancelled


logger = logging.getLogger(__name__)


def _response(data, status):
    response = JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


def _storage_errors(view):
    @wraps(view)
    def guarded(request, *args, **kwargs):
        try:
            return view(request, *args, **kwargs)
        except PreferenceStorageUnavailable as exc:
            logger.exception('support.storage.failed')
            configuration = exc.configuration_error
            return _response({
                'error': ('长期偏好数据库连接或表结构异常，请联系管理员检查配置。' if configuration else
                          '长期偏好服务暂不可用，请稍后重试；服务恢复后可继续当前咨询。'),
                'error_code': 'MEMORY_STORAGE_CONFIGURATION_ERROR' if configuration else 'MEMORY_STORAGE_UNAVAILABLE',
                'retryable': not configuration,
            }, 503)
        except (DatabaseError, InterfaceError) as exc:
            logger.exception('support.storage.failed')
            return _response({'error': '客服数据库服务暂不可用，请稍后再试。',
                              'error_code': 'SUPPORT_STORAGE_UNAVAILABLE', 'retryable': True}, 503)
    return guarded


def _buyer(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None, _response({'error': '请先登录后再使用智能客服。'}, 401)
    try:
        payload = jwt_decode(header[7:])
        user = UserProfile.objects.get(id=payload.get('id'))
    except (DatabaseError, InterfaceError):
        raise
    except Exception:
        return None, _response({'error': '登录状态已失效，请重新登录。'}, 401)
    if not user.is_active:
        return None, _response({'error': '登录状态已失效，请重新登录。'}, 401)
    if not user.is_customer():
        return None, _response({'error': '此入口仅供买家使用。'}, 403)
    return user, None


def _prepare_chat(request):
    user, error = _buyer(request)
    if error is not None:
        return error
    if len(request.body) > 10000:
        return _response({'error': '消息过长，请缩短后重试。'}, 413)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict) or set(body) - {'message', 'conversation_id', 'request_id', 'expected_revision', 'bundle_selection'}:
            raise ValueError('unknown input')
        message = body.get('message', '')
        selection = body.get('bundle_selection')
        if selection is not None:
            from .bundle_references import BUNDLE_ID
            if (not isinstance(selection, dict) or set(selection) != {'request_id', 'bundle_id'}
                    or not isinstance(selection['request_id'], str)
                    or not isinstance(selection['bundle_id'], str) or not BUNDLE_ID.fullmatch(selection['bundle_id'])):
                raise ValueError('invalid bundle selection')
            uuid.UUID(selection['request_id'])
    except (ValueError, TypeError, AttributeError):
        return _response({'error': '请求格式无效。'}, 400)
    if not isinstance(message, str) or not message.strip() or len(message) > 1000:
        return _response({'error': '请输入 1 至 1000 字的问题。'}, 400)
    try:
        request_id = uuid.UUID(body['request_id']) if 'request_id' in body else uuid.uuid4()
        conversation_id = uuid.UUID(body['conversation_id']) if body.get('conversation_id') else None
        expected = body.get('expected_revision')
        if expected is not None and (type(expected) is not int or expected < 0):
            raise ValueError('invalid revision')
    except (ValueError, TypeError, AttributeError):
        return _response({'error': '会话 ID、请求 ID 或修订号无效。'}, 400)
    request_hash = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True).encode('utf-8')).hexdigest()
    return dict(user=user, message=message, selection=selection, request_id=request_id,
                conversation_id=conversation_id, expected=expected, request_hash=request_hash)


@require_POST
@_storage_errors
def chat(request):
    prepared = _prepare_chat(request)
    if isinstance(prepared, JsonResponse):
        return prepared
    if 'text/event-stream' in request.headers.get('Accept', ''):
        from .streaming import event_response
        response = event_response(request, lambda: _chat_json(prepared))
        if response is None:
            return _response({'error':'当前咨询较多，请稍后重试。', 'error_code':'STREAM_BUSY', 'retryable':True},503)
        return response
    return _chat_json(prepared)


@_storage_errors
def _chat_json(prepared):
    user, message, selection = (prepared[k] for k in ('user','message','selection'))
    request_id, conversation_id, expected, request_hash = (prepared[k] for k in
        ('request_id','conversation_id','expected','request_hash'))
    try:
        previous = replay(user, request_id, request_hash)
        if previous is not None:
            return _response(previous, 200)
        conversation = None
        if conversation_id is not None:
            conversation = SupportConversation.objects.filter(pk=conversation_id, user=user).first()
            if conversation is None:
                return _response({'error': '会话不存在或无权访问。'}, 404)
        revision = conversation.revision if conversation else 0
        if expected is not None and expected != revision:
            raise ConversationConflict('会话已更新，请重新读取后再提交')
        # Keep authentication, ownership, revision and idempotency checks, while
        # skipping model configuration, PostgreSQL memory and business tools.
        from .workflow import fixed_result
        fixed = fixed_result(message) if selection is None else None
        if fixed is not None:
            response = dict(fixed['response'], pii_redacted=fixed.get('pii_redacted', False))
            progress('saving')
            response = commit_turn(user, conversation, revision, request_id, request_hash,
                                   fixed['safe_message'], response)
            return _response(response, 200)
    except StreamCancelled:
        return _response({'error':'本轮连接已关闭。','error_code':'CANCELLED','retryable':True},499)
    except ConversationConflict as exc:
        return _response({'error': str(exc)}, 409)
    safe_message, references = prepare_order_input(message)
    order_query_context = OrderQueryContext(owner_id=user.pk,
        conversation_id=conversation.pk if conversation else None, references=references)
    observation = None
    data_access = None
    try:
        from .workflow import build_graph
        from .model_client import lazy_configured_model
        from .configuration import effective_configuration
        from .telemetry import observe_agent
        from .tool_services import create_tool_handlers
        agent_config = effective_configuration()
        with observe_agent(agent_config) as observation:
            data_access = AgentDataAccess(config=agent_config, message=safe_message, owner_id=user.pk,
                conversation=conversation, references=references, selection=selection, order_context=order_query_context)
            if conversation or selection:
                progress('history')
            history = data_access.history() if conversation or selection else []
            memory = load_agent_preferences(data_access, safe_message, history)
            model = lazy_configured_model(agent_config)
            graph = build_graph(model, tool_factory=lambda state: create_tool_handlers(
                model, data_access.search,
                state['safe_message'], state['resolved_question'], state.get('recent_turns', []),
                memory,
                knowledge_context_chars=agent_config.retrieval_context_chars,
                order_query_context=order_query_context,
                data_access=data_access,
            ))
            result = graph.invoke({
                'message': safe_message, 'recent_turns': history, 'memory': memory,
                'owner_id': user.pk,
            }, config={'callbacks': [observation.callback] if observation.callback else []})
            observation.finish(result)
            if order_query_context.conversation_missing:
                raise ConversationConflict('咨询已删除，请开始新对话')
            if order_query_context.not_queryable and not any(
                    r['status'] in ('success','no_match','needs_clarification') for r in result['tool_results']):
                return _response({'error': '未找到可查询的订单。', 'error_code': 'ORDER_NOT_QUERYABLE'}, 404)
            if result['tool_results'] and all(r['status'] in ('error', 'skipped') for r in result['tool_results']):
                raise RuntimeError('All Agent tools failed')
            response = dict(result['response'], pii_redacted=safe_message != message.strip() or result.get('pii_redacted', False))
            response = attach_order_links(response, order_query_context)
            if observation.trace_id:
                response['trace_id'] = observation.trace_id
            progress('saving')
            response = commit_turn(
                user, conversation, revision, request_id, request_hash, safe_message, response,
                order_id=order_query_context.selected_order_id if order_query_context.binding_changed else None,
            )
    except StreamCancelled:
        return _response({'error':'本轮连接已关闭。','error_code':'CANCELLED','retryable':True},499)
    except ConversationConflict as exc:
        return _response({'error': str(exc)}, 409)
    except McpServiceError as exc:
        if exc.code == 'CONVERSATION_CONFLICT':
            return _response({'error': '会话已更新，请重新读取后再提交。', 'error_code': exc.code}, 409)
        if exc.code == 'ACCESS_DENIED':
            return _response({'error': '会话或所选对象不存在或无权访问。', 'error_code': exc.code}, 404)
        return _response({'error': '智能客服数据服务暂不可用，请稍后重试。',
                          'error_code': exc.code, 'retryable': exc.retryable}, 503)
    except Exception as exc:
        trace_id = observation.trace_id if observation else ''
        logger.exception('support.workflow.failed')
        error_response = {'error': '智能客服暂时无法响应，请稍后再试或联系人工客服。'}
        if trace_id:
            error_response['trace_id'] = trace_id
        return _response(error_response, 503)
    finally:
        if data_access is not None:
            data_access.close()
    return _response(response, 200)


def load_agent_preferences(data_access, message, history):
    """Only explicit preference tasks require memory; other recommendations may omit it."""
    explicit = bool(re.search(r'偏好|长期记忆|保存的喜好|saved preferences|my preferences', message, re.I))
    anchors = explicit_requests(message)
    recommendation = any(r.kind == 'recommendation' for r in anchors)
    pending = bool(history and (history[-1].get('dialogue_state') or {}).get('task') == 'recommendation' and not anchors)
    if not (explicit or recommendation or pending):
        return None
    try:
        progress('preferences')
        return data_access.preferences()
    except McpServiceError as exc:
        if explicit or exc.code in ('ACCESS_DENIED','CONVERSATION_CONFLICT'):
            raise
        data_access.preference_unavailable = True
        return None


@require_http_methods(['GET', 'PUT', 'DELETE'])
@_storage_errors
def preferences(request):
    user, error = _buyer(request)
    if error is not None:
        return error
    if request.method == 'GET':
        record = saved_preferences(user)
        return _response({'preferences': record['preferences'] if record else Preferences().model_dump()}, 200)
    if request.method == 'DELETE':
        BuyerMemory.objects.filter(owner_id=user.pk).delete()
        return _response({'preferences': Preferences().model_dump()}, 200)
    if len(request.body) > 3000:
        return _response({'error': '偏好内容过长。'}, 413)
    try:
        values = Preferences.model_validate(json.loads(request.body)).model_dump()
    except (ValueError, TypeError, ValidationError):
        return _response({'error': '请填写分类、品牌或商品名称偏好，每项最多 5 个、每个最多 40 字，不含个人信息。'}, 400)
    BuyerMemory.objects.update_or_create(owner_id=user.pk, defaults={'preferences': values})
    return _response({'preferences': values}, 200)


@require_http_methods(['GET'])
@_storage_errors
def conversation_list(request):
    user, error = _buyer(request)
    if error is not None:
        return error
    if not user.is_active:
        return _response({'error': '登录状态已失效，请重新登录。'}, 401)
    try:
        data = list_conversations(user, request.GET)
    except ValueError:
        return _response({'error': '历史咨询分页参数无效，请刷新列表后重试。'}, 400)
    return _response(data, 200)


@require_http_methods(['GET'])
@_storage_errors
def conversation_detail(request, conversation_id):
    user, error = _buyer(request)
    if error is not None:
        return error
    if not user.is_active:
        return _response({'error': '登录状态已失效，请重新登录。'}, 401)
    conversation = SupportConversation.objects.filter(pk=conversation_id, user=user).first()
    if conversation is None:
        return _response({'error': '会话不存在或无权访问。'}, 404)
    try:
        data = conversation_page(conversation, user, request.GET, default_limit=HISTORY_TURNS)
    except ValueError:
        return _response({'error': '对话记录分页参数无效，请重新打开该咨询。'}, 400)
    return _response(data, 200)
