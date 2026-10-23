"""Pure order intent contracts and lexical reference masking. No ORM imports."""
import re
import uuid
from typing import List, Literal, Optional

from pydantic import Field, model_validator

from .contracts import Contract
from .pii import redact


REFERENCE = r'ORDER_REF_[a-p]{8}_[1-9]'
REFERENCES = re.compile(REFERENCE)
LATEST = re.compile(r'最近(?:的)?一(?:笔|个|单)|最新|最后一(?:笔|个|单)|最后(?:的)?订单|\b(?:latest|last order)\b', re.I)
RECENT = re.compile(r'最近|近期|全部|所有|其他|别的|\b(?:recent|all|other)\b', re.I)
SELECTED = re.compile(r'这(?:个|笔|单)|那(?:个|笔|单)|该订单|所选|当前订单|现在|\b(?:this|that|selected)\b', re.I)
FOLLOW_UP = re.compile(r'(?:那)?(?:现在呢|现在怎么样|发货了吗|付款了吗|支付了吗|到哪了|什么状态)[？?。!！\s]*')
WRITE = re.compile(r'取消|退款|退货|改地址|修改地址|催发货|\b(?:cancel|refund|return|change address)\b', re.I)
UNSUPPORTED = re.compile(r'昨天|前天|上周|上月|去年|今年|红茶|绿茶|白茶|乌龙|黑茶|黄茶|商家|金额|'
                         r'第[一二三四五六七八九十\d]+(?:笔|个|单)|近期订单[一二三1-3]|\d{4}[-/年]\d', re.I)


class OrderSelector(Contract):
    type: Literal['latest', 'recent', 'selected', 'explicit'] = 'recent'
    reference: Optional[str] = Field(default=None, pattern=r'^' + REFERENCE + r'$')

    @model_validator(mode='after')
    def reference_scope(self):
        if (self.type == 'explicit') != (self.reference is not None):
            raise ValueError('Only explicit orders require a current-turn reference')
        return self


class OrderQuery(Contract):
    selector: OrderSelector = Field(default_factory=OrderSelector)
    topic: Literal['order_status', 'payment_status', 'shipping_status'] = 'order_status'


class OrderSummary(Contract):
    reference: str = Field(max_length=40)
    order_status: str = Field(max_length=40)
    payment_status: Literal['paid', 'unpaid', 'deposit_paid', 'balance_due', 'unknown']
    shipping_status: Literal['not_shipped', 'shipped', 'unknown']
    created_date: str = Field(pattern=r'^\d{4}-\d{2}-\d{2}$')


class OrderQueryData(Contract):
    answer: str = Field(max_length=1600)
    orders: List[OrderSummary] = Field(default_factory=list, max_length=3)
    queried_at: Optional[str] = None


class OrderQueryResult(Contract):
    status: Literal['success', 'no_match', 'needs_clarification', 'error']
    data: OrderQueryData


def prepare_order_input(message):
    """Extract candidates locally; random references never resolve without this map."""
    message = REFERENCES.sub('[无效订单引用]', message.strip())
    mapping = {}
    prefix = uuid.uuid4().hex[:8].translate(str.maketrans('0123456789', 'ghijklmnop'))

    def replace(match):
        candidate = match.group('id')
        if re.search(r'(?:手机|电话|证件|卡号)[^，,。；;]{0,8}$', match.string[max(0, match.start() - 12):match.start()]):
            return match.group(0)
        existing = next((key for key, value in mapping.items() if value == candidate), None)
        if existing:
            return '订单引用 ' + existing
        if len(mapping) >= 9:
            return '[过多订单引用]'
        token = 'ORDER_REF_{}_{}'.format(prefix, len(mapping) + 1)
        mapping[token] = candidate
        return '订单引用 ' + token

    labeled = re.compile(r'(?:订单(?:号|编号)|单号|\border\s*(?:id|number|#))\s*[:：#]?\s*'
                         r'(?P<id>[A-Za-z0-9_-]{6,64})(?![A-Za-z0-9_-])', re.I)
    safe = labeled.sub(replace, message)
    # Bare legacy numeric IDs are candidates only in an order question or as a
    # standalone reference. Phone/card-like data elsewhere stays ordinary PII.
    if re.search(r'订单|\border\b', message, re.I) or re.fullmatch(r'\d{10,24}', message):
        safe = re.sub(r'(?<![A-Za-z0-9_])(?P<id>\d{10,24})(?![A-Za-z0-9_])', replace, safe)
    return redact(safe), mapping


def rule_order_query(message):
    references = list(dict.fromkeys(REFERENCES.findall(message)))
    if references:
        selector = OrderSelector(type='explicit', reference=references[0])
    elif LATEST.search(message):
        selector = OrderSelector(type='latest')
    elif RECENT.search(message):
        selector = OrderSelector(type='recent')
    elif SELECTED.search(message) or FOLLOW_UP.fullmatch(message.strip()):
        selector = OrderSelector(type='selected')
    else:
        selector = OrderSelector(type='recent')
    topic = ('payment_status' if re.search(r'付款|支付|\bpa(?:y|id)\b', message, re.I) else
             'shipping_status' if re.search(r'发货|物流|到哪|\b(?:ship|shipping|delivery)\b', message, re.I) else
             'order_status')
    return OrderQuery(selector=selector, topic=topic)


def validate_order_query(query, request):
    """Check model slots again against this task's exact current-turn quote."""
    query = OrderQuery.model_validate(query)
    if re.search(r'(?:不要|不用|无需|不想|不必|别).{0,3}(?:查|看).{0,8}(?:订单|物流)', request):
        raise ValueError('本轮要求不查询订单，请明确其他需要处理的任务。')
    references = list(dict.fromkeys(REFERENCES.findall(request)))
    if len(references) > 1 or '[过多订单引用]' in request:
        raise ValueError('请一次提供一个订单号，以便明确要查询的订单。')
    if WRITE.search(request):
        raise ValueError('此工具仅查询订单、付款和发货状态；取消、退款或退货请进入“我的订单”办理。')
    if UNSUPPORTED.search(request):
        raise ValueError('目前支持最近订单、近期三笔订单或明确订单号查询，请补充订单号。')
    expected = rule_order_query(request)
    if query.selector != expected.selector or query.topic != expected.topic:
        raise ValueError('订单查询条件与本轮原话不一致，请明确订单及要查询的状态。')
    return query
