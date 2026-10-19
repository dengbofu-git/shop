import json
import logging
import hashlib
import uuid
from functools import wraps

from django.conf import settings
from django.db import DatabaseError
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.views.decorators.http import require_http_methods

from tea_saas.utils import jwt_decode
from users.models import UserProfile
from ai_storage.models import BuyerMemory

from .contracts import Preferences
from .context import (ConversationConflict, commit_turn, current_order_context,
                      recent_context, replay, saved_preferences, HISTORY_TURNS)
from .models import SupportConversation
from pydantic import ValidationError


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
        except DatabaseError as exc:
            logger.error('Customer support storage failed: %s', type(exc).__name__)
            return _response({'error': '客服数据库服务暂不可用，请稍后再试。'}, 503)
    return guarded


def _buyer(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return None, _response({'error': '请先登录后再使用智能客服。'}, 401)
    try:
        payload = jwt_decode(header[7:])
        user = UserProfile.objects.get(id=payload.get('id'))
    except DatabaseError:
        raise
    except Exception:
        return None, _response({'error': '登录状态已失效，请重新登录。'}, 401)
    if not user.is_customer():
        return None, _response({'error': '此入口仅供买家使用。'}, 403)
    return user, None


@require_POST
@_storage_errors
def chat(request):
    user, error = _buyer(request)
    if error is not None:
        return error
    if len(request.body) > 10000:
        return _response({'error': '消息过长，请缩短后重试。'}, 413)
    try:
        body = json.loads(request.body)
        if not isinstance(body, dict) or set(body) - {'message', 'conversation_id', 'request_id', 'expected_revision'}:
            raise ValueError('unknown input')
        message = body.get('message', '')
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
        history = recent_context(conversation)
        memory = saved_preferences(user)
    except ConversationConflict as exc:
        return _response({'error': str(exc)}, 409)
    if not settings.SUPPORT_API_KEY:
        return _response({'error': '智能客服尚未配置模型服务，请联系管理员。'}, 503)

    safe_message, order_context, selected_order_id = current_order_context(user, conversation, message)
    observation = None
    try:
        from .workflow import build_graph
        from .model_client import configured_model
        from .configuration import effective_configuration
        from .telemetry import observe_agent
        from .retrieval import retrieve_knowledge, retrieve_scoped_knowledge
        from .tool_services import create_tool_handlers
        agent_config = effective_configuration()
        with observe_agent(agent_config) as observation:
            model = configured_model(agent_config)
            graph = build_graph(model, tool_factory=lambda state: create_tool_handlers(
                model, lambda query: retrieve_knowledge(query, user.pk, agent_config),
                state['safe_message'], state['resolved_question'], state.get('recent_turns', []),
                memory, order_context,
                knowledge_context_chars=agent_config.retrieval_context_chars,
                scoped_knowledge_search=lambda query, category, scope: retrieve_scoped_knowledge(
                    query, user.pk, agent_config, category, scope),
            ))
            result = graph.invoke({
                'message': safe_message, 'recent_turns': history, 'memory': memory, 'order_context': order_context,
                'owner_id': user.pk,
            }, config={'callbacks': [observation.callback] if observation.callback else []})
            observation.finish(result)
            if result['tool_results'] and all(r['status'] in ('error', 'skipped') for r in result['tool_results']):
                raise RuntimeError('All Agent tools failed')
            response = dict(result['response'], pii_redacted=safe_message != message.strip() or result.get('pii_redacted', False))
            if observation.trace_id:
                response['trace_id'] = observation.trace_id
            response = commit_turn(
                user, conversation, revision, request_id, request_hash, safe_message, response,
                order_id=selected_order_id if 'after_sales' in result['intents'] else None,
            )
    except ConversationConflict as exc:
        return _response({'error': str(exc)}, 409)
    except Exception as exc:
        trace_id = observation.trace_id if observation else ''
        logger.error('Customer support workflow failed: %s trace_id=%s', type(exc).__name__, trace_id or 'unavailable')
        error_response = {'error': '智能客服暂时无法响应，请稍后再试或联系人工客服。'}
        if trace_id:
            error_response['trace_id'] = trace_id
        return _response(error_response, 503)
    return _response(response, 200)


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
def conversation_detail(request, conversation_id):
    user, error = _buyer(request)
    if error is not None:
        return error
    conversation = SupportConversation.objects.filter(pk=conversation_id, user=user).first()
    if conversation is None:
        return _response({'error': '会话不存在或无权访问。'}, 404)
    turns = list(conversation.turns.order_by('-sequence')[:HISTORY_TURNS])
    return _response({'conversation_id': str(conversation.pk), 'revision': conversation.revision,
                      'turns': [{'message': turn.user_text, 'response': turn.response} for turn in reversed(turns)]}, 200)
