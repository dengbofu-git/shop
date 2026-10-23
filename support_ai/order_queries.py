"""Application-owned, read-only order tool. Private identity never enters plans."""
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.utils.crypto import salted_hmac, constant_time_compare
from django.core import signing
from pydantic import ValidationError
import pytz

from orders.models import OrderInfo, STATUS_CHOICES, TRIAL_STATUS_CHOICES, PRESALE_STATUS_CHOICES
from users.models import UserProfile

from .context import HISTORY_HOURS
from .models import SupportConversation, SupportTurn
from .order_contracts import REFERENCES, OrderQuery, OrderQueryResult, validate_order_query


PAGE_SIZE = 20
CURSOR_SALT = 'support-order-results-v1'
ORDER_TIMEZONE = pytz.timezone('Asia/Shanghai')


@dataclass
class OrderQueryContext:
    owner_id: Optional[int] = field(default=None, repr=False)
    conversation_id: object = field(default=None, repr=False)
    references: dict = field(default_factory=dict, repr=False)
    active_order_id: str = field(default='', repr=False)
    active_order_at: object = field(default=None, repr=False)
    binding_changed: bool = field(default=False, init=False)
    selected_order_id: str = field(default='', init=False, repr=False)
    not_queryable: bool = field(default=False, init=False)
    conversation_missing: bool = field(default=False, init=False)
    previous_page: dict = field(default_factory=dict, repr=False)


def _result(status, answer, orders=None, queried_at=None, **pagination):
    return OrderQueryResult.model_validate({'status': status,
        'data': {'answer': answer, 'orders': orders or [], 'queried_at': queried_at,
                 'returned_count': len(orders or []), **pagination}}).model_dump()


def _cursor_owner(owner_id):
    return salted_hmac(CURSOR_SALT, str(owner_id), algorithm='sha256').hexdigest()


def _next_page(context, query):
    previous = context.previous_page
    if context.conversation_id:
        stored = SupportTurn.objects.filter(conversation_id=context.conversation_id,
            user_id=context.owner_id, created_at__gte=timezone.now() - timedelta(hours=HISTORY_HOURS),
            response__has_key='order_result').order_by('-sequence').values_list('response', flat=True).first()
        previous = stored.get('order_result', {}) if stored else {}
    if not previous.get('has_more') or not previous.get('next_cursor'):
        raise ValueError('没有可继续的订单分页，请重新查询全部订单或指定日期范围。')
    try:
        data = signing.loads(previous['next_cursor'], salt=CURSOR_SALT, max_age=86400)
        base = query.model_copy(update={'page': 'first'}).model_dump()
        snapshot = parse_datetime(data['snapshot_at'])
        offset = data['offset']
        if (not constant_time_compare(data['owner'], _cursor_owner(context.owner_id))
                or data['query'] != base or type(offset) is not int or offset < PAGE_SIZE
                or snapshot is None or not timezone.is_aware(snapshot)):
            raise ValueError('Invalid cursor binding')
    except (signing.BadSignature, KeyError, TypeError, ValueError):
        raise ValueError('订单分页已失效或查询条件已改变，请重新查询。') from None
    return offset, snapshot


def binding_for_commit(owner_id, order_id):
    """Recheck a successful tool selection before persisting its private binding."""
    if order_id and OrderInfo.objects.filter(pk=order_id, user_profile_id=owner_id, buyer_hidden=False).exists():
        return order_id
    return ''


def _project(row, label):
    kind = row['order_type']
    status = (row['trialorder__status'] if kind == 'trial' else
              row['presaleorder__status'] if kind == 'presale' else row['status'])
    choices = {'standard': STATUS_CHOICES, 'trial': TRIAL_STATUS_CHOICES, 'presale': PRESALE_STATUS_CHOICES}
    status_text = dict(choices.get(kind, ())).get(status, '状态暂无法确认')
    paid = {'standard': (2, 3, 4), 'trial': (2, 3, 4, 5), 'presale': (4, 5, 6)}
    unshipped = {'standard': (1, 2), 'trial': (1, 2), 'presale': (1, 2, 3, 4)}
    shipped = {'standard': (3, 4), 'trial': (3, 4, 5), 'presale': (5, 6)}
    payment = 'unknown'
    if status in paid.get(kind, ()):
        payment = 'paid'
    elif status == 1 and kind in choices:
        payment = 'unpaid'
    elif kind == 'presale' and status in (2, 3):
        payment = 'deposit_paid' if status == 2 else 'balance_due'
    shipping = ('not_shipped' if status in unshipped.get(kind, ()) else
                'shipped' if status in shipped.get(kind, ()) else 'unknown')
    return {'reference': label, 'order_status': status_text,
            'payment_status': payment, 'shipping_status': shipping,
            'created_date': timezone.localtime(row['created_time'], ORDER_TIMEZONE).date().isoformat()}


def query_orders(query, context, request):
    """Only invoked by get_order_status after the server selects the fixed tool."""
    if not isinstance(context, OrderQueryContext) or type(context.owner_id) is not int:
        return _result('needs_clarification', '请先绑定并登录买家账号后查询本人订单。')
    user = UserProfile.objects.filter(pk=context.owner_id, is_active=True).first()
    if user is None or not user.is_customer():
        return _result('needs_clarification', '登录状态或买家权限已变化，请重新登录。')
    if context.references and set(REFERENCES.findall(request)) != set(context.references):
        return _result('needs_clarification', '本轮订单引用未完整保留，请一次明确提供一个订单号。')
    try:
        query = validate_order_query(query, request)
    except ValidationError:
        return _result('needs_clarification', '订单查询参数无效，请明确要查询的订单和状态。')
    except ValueError as exc:
        return _result('needs_clarification', str(exc))
    bound_id, bound_at = context.active_order_id, context.active_order_at
    if context.conversation_id:
        conversation = SupportConversation.objects.filter(pk=context.conversation_id, user_id=user.pk).first()
        if conversation is None:
            context.conversation_missing = True
            return _result('error', '咨询不存在或已删除，请开始新对话。')
        bound_id, bound_at = conversation.active_order_id, conversation.active_order_at
    selector = query.selector
    selected_id = ''
    if selector.type == 'explicit':
        selected_id = context.references.get(selector.reference, '')
        if not selected_id:
            return _result('needs_clarification', '订单引用已失效，请重新提供订单号。')
    elif selector.type == 'selected':
        if not bound_id or bound_at is None or bound_at < timezone.now() - timedelta(hours=HISTORY_HOURS):
            return _result('needs_clarification', '当前没有有效的所选订单，请提供订单号，或说“查询最近订单”。')
        selected_id = bound_id
    orders = OrderInfo.objects.filter(user_profile_id=user.pk, buyer_hidden=False)
    if selected_id:
        orders = orders.filter(pk=selected_id)
    period = query.filters.created_date
    if period:
        start = ORDER_TIMEZONE.localize(datetime.combine(date.fromisoformat(period.start), time.min))
        end = ORDER_TIMEZONE.localize(datetime.combine(date.fromisoformat(period.end) + timedelta(days=1), time.min))
        orders = orders.filter(created_time__gte=start, created_time__lt=end)
    offset, snapshot = 0, timezone.now()
    if query.page == 'next':
        try:
            offset, snapshot = _next_page(context, query)
        except ValueError as exc:
            return _result('needs_clarification', str(exc))
    pagination = {'query': query.model_dump()}
    if selector.type == 'all':
        orders = orders.filter(created_time__lte=snapshot)
        pagination.update(total_count=orders.count(), page_offset=offset, snapshot_at=snapshot.isoformat())
    limit = PAGE_SIZE if selector.type == 'all' else 3 if selector.type == 'recent' else 1
    # SQL projection excludes recipient, address, phone, payment identifiers and
    # child-order private text. Subtype states are read without N+1 lookups.
    rows = list(orders.order_by('-created_time', '-order_id').values(
        'order_id', 'order_type', 'status', 'created_time',
        'trialorder__status', 'presaleorder__status')[offset:offset + limit + (selector.type == 'all')])
    has_more = selector.type == 'all' and len(rows) > limit
    rows = rows[:limit]
    if has_more:
        pagination.update(has_more=True, next_cursor=signing.dumps({
            'owner': _cursor_owner(context.owner_id),
            'query': query.model_copy(update={'page': 'first'}).model_dump(),
            'offset': offset + limit, 'snapshot_at': snapshot.isoformat()}, salt=CURSOR_SALT, compress=True))
    queried_at = timezone.now().isoformat()
    if not rows:
        context.not_queryable = selector.type == 'explicit'
        result = _result('no_match', '未找到您可访问的匹配订单，请在“我的订单”中核对。', queried_at=queried_at, **pagination)
        context.binding_changed, context.selected_order_id = True, ''
        return result
    data = [_project(row, '匹配订单{}'.format(offset + i + 1) if selector.type == 'all' else
                     '近期订单{}'.format(i + 1) if selector.type == 'recent' else '当前所选订单')
            for i, row in enumerate(rows)]
    labels = {'paid': '已付款', 'unpaid': '待付款', 'deposit_paid': '已付定金', 'balance_due': '待付尾款',
              'not_shipped': '尚未发货', 'shipped': '已发货', 'unknown': '暂无法确认'}
    lines = ['创建日期：{} 至 {}（北京时间，含首尾日期）。'.format(period.start, period.end)] if period else []
    for order in data:
        detail = order['order_status']
        if query.topic != 'order_status':
            detail += '；{}：{}'.format('付款状态' if query.topic == 'payment_status' else '发货状态', labels[order[query.topic]])
        lines.append('{}（{}）：{}。'.format(order['reference'], order['created_date'], detail))
    if selector.type == 'recent':
        lines.append('以上最多显示近期三笔订单；查询其中一笔的后续状态，请提供该订单号。')
    elif selector.type == 'all':
        lines.append('共匹配{}笔订单，本页显示第{}至{}笔，每页最多{}笔。'.format(
            pagination['total_count'], offset + 1, offset + len(data), PAGE_SIZE))
        if has_more:
            lines.append('回复“下一页”继续查看。隐藏或删除订单后，分页结果可能变化。')
    if query.topic == 'payment_status':
        lines.append('付款状态依据订单业务状态解释，不代表独立的支付到账核验。')
    lines.append('查询时间：{}。订单状态可能随后变化，请以订单详情为准。'.format(queried_at))
    result = _result('success', '\n'.join(lines), data, queried_at, **pagination)
    context.binding_changed = True
    context.selected_order_id = rows[0]['order_id'] if selector.type not in ('recent', 'all') else ''
    return result
