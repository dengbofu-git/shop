"""Application-owned persistence and ownership checks, outside the Agent graph."""

import json
import re
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from users.models import UserProfile
from ai_storage.models import BuyerMemory
from orders.models import OrderInfo

from .contracts import Preferences
from .models import SupportConversation, SupportTurn
from .pii import redact


HISTORY_HOURS = 24
HISTORY_TURNS = 6
HISTORY_CHARS = 6000


class ConversationConflict(Exception):
    pass


def saved_preferences(user):
    record = BuyerMemory.objects.filter(owner_id=user.pk).first()
    if record is None:
        return None
    data = Preferences.model_validate(record.preferences).model_dump()
    return {'id': 'preference:{}:{}'.format(record.pk, record.updated_at.isoformat()), 'preferences': data}


def recent_context(conversation):
    if conversation is None:
        return []
    turns = conversation.turns.filter(created_at__gte=timezone.now() - timedelta(hours=HISTORY_HOURS)).order_by('-sequence')[:HISTORY_TURNS]
    return context_from_turns(turns)


def context_from_turns(turns):
    """Build bounded model context from committed turns, newest first."""
    result = []
    remaining = HISTORY_CHARS - 2  # JSON array brackets.
    for index, turn in enumerate(turns):
        if index >= HISTORY_TURNS:
            break
        # Only committed turns and redacted text enter the model; no raw business objects.
        text = redact(turn.user_text)
        answer = redact(turn.answer)[:1500]
        item = {'turn_id': 'turn-{}'.format(turn.pk), 'user_text': text,
                'assistant_text': answer, 'intent': turn.intent}
        # Preserve display order and names to resolve "the second product". Historical
        # prices/stock are deliberately excluded; names identify products, not facts.
        products = turn.response.get('recommendations', [])[:12]
        if products:
            item['product_references'] = [
                {'position': i + 1, 'name': redact(str(p.get('name', '')))[:100],
                 'product_name': redact(str(p.get('product_name', '')))[:100]}
                for i, p in enumerate(products)
            ]
            for reference, product in zip(item['product_references'], products):
                if product.get('group_position'):
                    reference['group_position'] = product['group_position']
                    reference['group_category'] = redact(product.get('group_category', ''))[:40]
        if turn.response.get('recommendation_groups'):
            item['recommendation_groups'] = [
                {'position': group['position'], 'category': redact(group['category'])[:40]}
                for group in turn.response['recommendation_groups'][:6]
            ]
        if turn.response.get('explained_categories'):
            item['explained_categories'] = list(turn.response['explained_categories'][:6])
        size = len(json.dumps(item, ensure_ascii=False)) + (2 if result else 0)
        # A long grouped reply must not evict the entire newest turn. Prefer
        # product identity references over verbose historical assistant prose.
        if not result:
            while size > remaining and len(item['assistant_text']) > 240:
                item['assistant_text'] = item['assistant_text'][:-200]
                size = len(json.dumps(item, ensure_ascii=False))
            while size > remaining and item.get('product_references'):
                item['product_references'].pop()
                size = len(json.dumps(item, ensure_ascii=False))
        if size > remaining:
            break
        remaining -= size
        result.append(item)
    return list(reversed(result))


def current_order_context(user, conversation, message):
    """Resolve a private order reference, rechecking ownership and live status."""
    own_orders = OrderInfo.objects.filter(user_profile=user).order_by('-created_time')
    owned_ids = list(own_orders.values_list('order_id', flat=True))
    selected = next((oid for oid in sorted(owned_ids, key=len, reverse=True)
                     if re.search(r'(?<![A-Za-z0-9_-])' + re.escape(oid) + r'(?![A-Za-z0-9_-])', message)), '')
    explicit_unknown = bool(re.search(
        r'(?<!\d)\d{10,}(?!\d)|(?:订单号|订单编号|单号|order\s*(?:id|number|#))\s*[:：#]?\s*[A-Za-z0-9-]{6,64}',
        message, re.I)) and not selected
    reset = bool(re.search(r'最近|近期|全部|所有|其他|另[一个]|别的|\b(?:recent|latest|other)\b|all\s+orders', message, re.I))
    if (not selected and not explicit_unknown and not reset and conversation is not None
            and conversation.active_order_at is not None
            and conversation.active_order_at >= timezone.now() - timedelta(hours=HISTORY_HOURS)
            and conversation.active_order_id in owned_ids):
        selected = conversation.active_order_id
    orders = own_orders.filter(order_id=selected) if selected else ([] if explicit_unknown else own_orders[:3])
    data = [{'order': '当前会话所选订单' if selected else '近期订单{}'.format(i + 1),
             'status': redact(order.get_status_display_text()),
             'created_date': order.created_time.date().isoformat()}
            for i, order in enumerate(orders)]
    return redact(message.strip(), owned_ids), json.dumps(data, ensure_ascii=False), selected


def replay(user, request_id, request_hash):
    turn = SupportTurn.objects.filter(user=user, request_id=request_id).first()
    if turn is None:
        return None
    if turn.request_hash != request_hash:
        raise ConversationConflict('相同请求 ID 不能用于不同内容')
    return turn.response


@transaction.atomic
def commit_turn(user, conversation, revision, request_id, request_hash, message, response, order_id=None):
    # Serialize only the short commit, including retries of a first/new conversation.
    UserProfile.objects.select_for_update().get(pk=user.pk)
    existing = replay(user, request_id, request_hash)
    if existing is not None:
        return existing
    if conversation is None:
        current = SupportConversation.objects.create(user=user)
    else:
        current = SupportConversation.objects.select_for_update().get(pk=conversation.pk, user=user)
        if current.revision != revision:
            raise ConversationConflict('会话已更新，请重新读取后再提交')
    current.revision += 1
    fields = ['revision', 'updated_at']
    if order_id is not None:
        current.active_order_id = order_id if OrderInfo.objects.filter(pk=order_id, user_profile=user).exists() else ''
        current.active_order_at = timezone.now() if current.active_order_id else None
        fields += ['active_order_id', 'active_order_at']
    current.save(update_fields=fields)
    result = dict(response, conversation_id=str(current.pk), revision=current.revision, request_id=str(request_id))
    SupportTurn.objects.create(conversation=current, user=user, request_id=request_id, request_hash=request_hash,
                               sequence=current.revision, user_text=message, answer=result['answer'],
                               intent=result['intent'], response=result)
    return result
