"""Owner-scoped, read-only history projections; display paging is not model memory."""
import re
import uuid

from django.core import signing
from django.db.models import OuterRef, Q, Subquery
from django.utils.dateparse import parse_datetime
from django.utils.timezone import is_aware

from .models import SupportConversation, SupportTurn
from .pii import redact


CURSOR_SALT = 'support-conversation-list-v1'
MAX_PAGE_SIZE = 50


def page_number(value, default, maximum=MAX_PAGE_SIZE):
    if value is None:
        return default
    if not isinstance(value, str) or not re.fullmatch(r'[1-9][0-9]{0,9}', value):
        raise ValueError('Invalid pagination')
    parsed = int(value)
    if parsed > maximum:
        raise ValueError('Invalid pagination')
    return parsed


def history_value(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, list):
        return [history_value(item) for item in value]
    if isinstance(value, dict):
        return {key: history_value(item) for key, item in value.items()}
    return value


def title_for(text):
    clean = ' '.join(redact(text or '').split())
    return clean[:60] + ('…' if len(clean) > 60 else '') if clean else '未命名咨询'


def summary(conversation, first_message):
    return {'conversation_id': str(conversation.pk), 'title': title_for(first_message),
            'turn_count': conversation.revision,
            'created_at': conversation.created_at.isoformat(), 'updated_at': conversation.updated_at.isoformat()}


def list_conversations(user, query):
    if set(query) - {'limit', 'cursor'} or any(len(query.getlist(key)) != 1 for key in query):
        raise ValueError('Invalid pagination')
    limit = page_number(query.get('limit'), 20)
    first_turn = SupportTurn.objects.filter(conversation_id=OuterRef('pk'), user=user).order_by('sequence')
    conversations = SupportConversation.objects.filter(user=user, revision__gt=0).annotate(
        first_message=Subquery(first_turn.values('user_text')[:1])).exclude(first_message__isnull=True)
    cursor = query.get('cursor')
    if cursor is not None:
        try:
            if not cursor or len(cursor) > 1000:
                raise ValueError('Invalid cursor')
            data = signing.loads(cursor, salt=CURSOR_SALT, max_age=86400)
            if not isinstance(data, dict) or data.get('user') != str(user.pk):
                raise ValueError('Invalid cursor owner')
            date = parse_datetime(data['updated_at'])
            identity = uuid.UUID(data['id'])
            if date is None or not is_aware(date):
                raise ValueError('Invalid cursor time')
        except (signing.BadSignature, KeyError, TypeError, ValueError, AttributeError):
            raise ValueError('Invalid pagination') from None
        conversations = conversations.filter(Q(updated_at__lt=date) | Q(updated_at=date, pk__lt=identity))
    rows = list(conversations.order_by('-updated_at', '-pk')[:limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    next_cursor = None
    if has_more:
        last = rows[-1]
        next_cursor = signing.dumps({'user':str(user.pk), 'updated_at':last.updated_at.isoformat(),
                                     'id':str(last.pk)}, salt=CURSOR_SALT, compress=True)
    return {'conversations':[summary(row, row.first_message) for row in rows],
            'has_more':has_more, 'next_cursor':next_cursor}


def conversation_page(conversation, user, query, default_limit):
    if set(query) - {'limit', 'before_sequence'} or any(len(query.getlist(key)) != 1 for key in query):
        raise ValueError('Invalid pagination')
    limit = page_number(query.get('limit'), default_limit)
    before = page_number(query.get('before_sequence'), None, maximum=2147483647)
    turns = conversation.turns.filter(user=user)
    first_message = turns.order_by('sequence').values_list('user_text', flat=True).first()
    if before is not None:
        turns = turns.filter(sequence__lt=before)
    rows = list(turns.order_by('-sequence')[:limit + 1])
    has_more = len(rows) > limit
    rows = rows[:limit]
    return {**summary(conversation, first_message), 'revision':conversation.revision,
            'turns':[{'sequence':row.sequence, 'created_at':row.created_at.isoformat(),
                      'message':redact(row.user_text), 'response':history_value(row.response)} for row in reversed(rows)],
            'has_more':has_more, 'next_before_sequence':rows[-1].sequence if has_more else None}
