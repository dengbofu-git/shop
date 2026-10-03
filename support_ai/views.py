import json
import logging
import re

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from dadashop.utils import jwt_decode
from orders.models import OrderInfo
from users.models import UserProfile

from .pii import redact


logger = logging.getLogger(__name__)


def _response(data, status):
    response = JsonResponse(data, status=status, json_dumps_params={'ensure_ascii': False})
    response['Cache-Control'] = 'no-store'
    return response


@require_POST
def chat(request):
    header = request.headers.get('Authorization', '')
    if not header.startswith('Bearer '):
        return _response({'error': '请先登录后再使用智能客服。'}, 401)
    try:
        payload = jwt_decode(header[7:])
        user = UserProfile.objects.get(id=payload.get('id'))
    except Exception:
        return _response({'error': '登录状态已失效，请重新登录。'}, 401)
    if not user.is_customer():
        return _response({'error': '此入口仅供买家使用。'}, 403)
    if len(request.body) > 10000:
        return _response({'error': '消息过长，请缩短后重试。'}, 413)
    try:
        message = json.loads(request.body).get('message', '')
    except (ValueError, TypeError, AttributeError):
        return _response({'error': '请求格式无效。'}, 400)
    if not isinstance(message, str) or not message.strip() or len(message) > 1000:
        return _response({'error': '请输入 1 至 1000 字的问题。'}, 400)
    if not settings.SUPPORT_API_KEY:
        return _response({'error': '智能客服尚未配置模型服务，请联系管理员。'}, 503)

    # The graph and optional tracing receive only locally redacted text. An order
    # identifier is retained in memory only to query orders owned by this user.
    own_orders = OrderInfo.objects.filter(user_profile=user).order_by('-created_time')
    owned_ids = list(own_orders.values_list('order_id', flat=True))
    matched_order_id = next((oid for oid in owned_ids if oid in message), '')
    safe_message = redact(message.strip(), owned_ids)
    def order_context_provider():
        if matched_order_id:
            relevant_orders = own_orders.filter(order_id=matched_order_id)
        elif re.search(r'(?<!\d)\d{10,}(?!\d)', message):
            relevant_orders = []
        else:
            relevant_orders = own_orders[:3]
        return json.dumps([
            {
                'order': '所提订单' if matched_order_id else '近期订单',
                'status': redact(order.get_status_display_text()),
                'created_date': order.created_time.date().isoformat(),
            }
            for order in relevant_orders
        ], ensure_ascii=False)
    try:
        from .workflow import build_graph, configured_model
        result = build_graph(configured_model(), order_context_provider).invoke({'message': safe_message})
    except Exception as exc:
        logger.error('Customer support workflow failed: %s', type(exc).__name__)
        return _response({'error': '智能客服暂时无法响应，请稍后再试或联系人工客服。'}, 503)
    return _response({
        'answer': result['answer'],
        'intent': result['intent'],
        'confidence': round(result['scores'].get(result['intent'], 0), 2),
        'pii_redacted': safe_message != message.strip() or result.get('pii_redacted', False),
    }, 200)
