"""Application-owned persistence and ownership checks, outside the Agent graph."""

import json
from datetime import timedelta

from django.db import DatabaseError, InterfaceError, connections, transaction
from django.utils import timezone

from users.models import UserProfile
from ai_storage.models import BuyerMemory

from .contracts import Preferences, RequiredConditions, QueryConditions
from .models import SupportConversation, SupportTurn
from .pii import redact
from .bundle_references import compact_bundle_references


HISTORY_HOURS = 24
HISTORY_TURNS = 6
HISTORY_CHARS = 6000


def recommendation_basis(response):
    """Bounded server-saved selection filters, only for explaining past choices."""
    raw = response.get('recommendation_basis') or response.get('product_intent') or {}
    if not isinstance(raw, dict):
        return {}
    try:
        basis = {'required':RequiredConditions.model_validate(raw.get('required', {})).model_dump(),
                 'preferred':QueryConditions.model_validate(raw.get('preferred', {})).model_dump(),
                 'excluded':QueryConditions.model_validate(raw.get('excluded', {})).model_dump()}
    except ValueError:
        return {}
    return basis if any(value for part in basis.values() for value in part.values()) else {}


class ConversationConflict(Exception):
    pass


class PreferenceStorageUnavailable(DatabaseError):
    """A failed prerequisite read; never treat unavailable storage as no memory."""
    def __init__(self, configuration_error=False):
        super().__init__('Preference storage is unavailable')
        self.configuration_error = configuration_error


def _preference_connection_failure(exc):
    cause = exc.__cause__ or exc
    code = getattr(cause, 'pgcode', None) or ''
    text = str(cause).lower()
    configuration = code in ('28P01', '28000', '42P01', '42703', '3D000', '42501') or any(
        value in text for value in ('password authentication failed', 'does not exist', 'permission denied'))
    stale = code.startswith('08') or code in ('57P01', '57P02', '57P03') or any(
        value in text for value in ('server closed the connection', 'connection already closed',
            'connection not open', 'ssl connection has been closed', 'ssl syscall error: eof detected'))
    return stale and not configuration, configuration


def saved_preferences(user):
    for attempt in range(2):
        try:
            record = BuyerMemory.objects.filter(owner_id=user.pk).first()
            break
        except (DatabaseError, InterfaceError) as exc:
            stale, configuration = _preference_connection_failure(exc)
            connection = connections['ai_storage']
            # Retry only this read, once, on a known broken transport. Never
            # replay the workflow/commit, change request IDs, or retry writes.
            if attempt == 0 and stale and not connection.in_atomic_block:
                connection.close()
                continue
            raise PreferenceStorageUnavailable(configuration) from exc
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
        # These annotations originate in a committed application result, not a
        # model-authored context list. Bind the interpretation to this exact turn.
        purchase = (turn.response.get('product_intent') or
                    (turn.response.get('dialogue_state') or {}).get('purchase') or {})
        scope_evidence = [{key: evidence[key] for key in ('field', 'value', 'quote', 'context_turn_id')}
            for evidence in purchase.get('evidence', [])
            if evidence.get('context_turn_id') and evidence.get('source') == 'CURRENT'
            and evidence.get('field') == 'required.price_basis' and evidence.get('value') in ('unit', 'total')
            and evidence.get('quote') == text][:1]
        if scope_evidence:
            item['budget_scope_evidence'] = scope_evidence
        if index == 0 and turn.response.get('dialogue_state'):
            # Only application-committed JSON is admitted; clients cannot submit
            # state. Bind this turn's CURRENT evidence to its real persisted ID.
            from .semantic_planning import DialogueState
            try:
                snapshot = DialogueState.model_validate(turn.response['dialogue_state'])
                if snapshot.purchase:
                    for evidence in snapshot.purchase.evidence:
                        if evidence.source == 'CURRENT':
                            if evidence.quote not in text:
                                raise ValueError('Invalid saved evidence')
                            evidence.source = 'CONTEXT'
                            evidence.source_id = item['turn_id']
                if len(json.dumps(snapshot.model_dump(), ensure_ascii=False)) > 3000:
                    snapshot = DialogueState(status='pending', task=snapshot.task,
                                             missing_fields=['details'])
                item['dialogue_state'] = snapshot.model_dump()
            except ValueError:
                # An invalid latest snapshot is an explicit boundary; never
                # search older turns and revive a different pending task.
                item['dialogue_state'] = DialogueState().model_dump()
        # Preserve display order and names to resolve "the second product". Historical
        # prices/stock are deliberately excluded; names identify products, not facts.
        products = (turn.response.get('recommendations') or turn.response.get('recommendation_references')
                    or turn.response.get('explained_products') or [])[:12]
        if products:
            item['product_references'] = [
                {'position': i + 1, 'name': redact(str(p.get('name', '')))[:100],
                 'product_name': redact(str(p.get('product_name', '')))[:100]}
                for i, p in enumerate(products)
            ]
            for reference, product in zip(item['product_references'], products):
                # IDs originate only from application-owned tool results, never
                # from the resolver or user text. Historical price/stock stay out.
                if type(product.get('sku_id')) is int and product['sku_id'] > 0:
                    reference['sku_id'] = product['sku_id']
                if product.get('category'):
                    reference['category'] = redact(str(product['category']))[:40]
                if product.get('group_position'):
                    reference['group_position'] = product['group_position']
                    reference['group_category'] = redact(product.get('group_category', ''))[:40]
                if product.get('position_in_group'):
                    reference['position_in_group'] = product['position_in_group']
            basis = recommendation_basis(turn.response)
            if basis:
                item['recommendation_basis'] = basis
        if turn.response.get('recommendation_groups'):
            item['recommendation_groups'] = [
                {'position': group['position'], 'category': redact(group['category'])[:40]}
                for group in turn.response['recommendation_groups'][:6]
            ]
        if turn.response.get('explained_categories'):
            item['explained_categories'] = list(turn.response['explained_categories'][:6])
        bundle_refs = compact_bundle_references(turn.response)
        if bundle_refs:
            item['recommendation_bundles'] = bundle_refs
            item['primary_bundle_id'] = turn.response.get('primary_bundle_id') or bundle_refs[0]['bundle_id']
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
            while size > remaining and item.get('recommendation_bundles'):
                item['recommendation_bundles'].pop()
                size = len(json.dumps(item, ensure_ascii=False))
        if size > remaining:
            break
        remaining -= size
        result.append(item)
    return list(reversed(result))


def current_order_context(user, conversation, message):
    """Legacy adapter for old local callers; HTTP/preview use lazy order tools."""
    from .order_contracts import prepare_order_input, rule_order_query
    from .order_queries import OrderQueryContext, query_orders
    safe, references = prepare_order_input(message)
    context = OrderQueryContext(owner_id=user.pk, references=references,
        conversation_id=getattr(conversation, 'pk', None),
        active_order_id=getattr(conversation, 'active_order_id', ''),
        active_order_at=getattr(conversation, 'active_order_at', None))
    queried = query_orders(rule_order_query(safe), context, safe)
    return safe, json.dumps(queried['data']['orders'], ensure_ascii=False), context.selected_order_id


def select_bundle_context(user, conversation, history, selection):
    """Apply a browser selection only to an owned, recent, saved result."""
    if conversation is None:
        return False
    turn = SupportTurn.objects.filter(user=user, conversation=conversation,
        request_id=selection['request_id'], created_at__gte=timezone.now() - timedelta(hours=HISTORY_HOURS)).first()
    if turn is None:
        return False
    item = next((row for row in history if row['turn_id'] == 'turn-{}'.format(turn.pk)), None)
    if item is None:
        return False
    bundle = next((b for b in item.get('recommendation_bundles', [])
                   if b['bundle_id'] == selection['bundle_id']), None)
    if bundle is None or not bundle.get('items'):
        return False
    item['selected_bundle_id'] = bundle['bundle_id']
    item['product_references'] = list(bundle['items'])
    return True


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
        current = SupportConversation.objects.select_for_update().filter(pk=conversation.pk, user=user).first()
        if current is None:
            raise ConversationConflict('咨询已删除，请开始新对话')
        if current.revision != revision:
            raise ConversationConflict('会话已更新，请重新读取后再提交')
    current.revision += 1
    fields = ['revision', 'updated_at']
    if order_id is not None:
        from .order_queries import binding_for_commit
        current.active_order_id = binding_for_commit(user.pk, order_id)
        current.active_order_at = timezone.now() if current.active_order_id else None
        fields += ['active_order_id', 'active_order_at']
    current.save(update_fields=fields)
    result = dict(response, conversation_id=str(current.pk), revision=current.revision, request_id=str(request_id))
    SupportTurn.objects.create(conversation=current, user=user, request_id=request_id, request_hash=request_hash,
                               sequence=current.revision, user_text=message, answer=result['answer'],
                               intent=result['intent'], response=result)
    return result
