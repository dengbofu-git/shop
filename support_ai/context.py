"""Application-owned persistence and ownership checks, outside the Agent graph."""

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from users.models import UserProfile
from ai_storage.models import BuyerMemory

from .contracts import Preferences
from .models import SupportConversation, SupportTurn
from .pii import redact


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
    turns = conversation.turns.filter(created_at__gte=timezone.now() - timedelta(hours=24)).order_by('-sequence')[:6]
    result = []
    remaining = 6000
    for turn in turns:
        # Only committed turns and redacted text enter the model; no raw business objects.
        text = redact(turn.user_text)
        answer = redact(turn.answer)[:1500]
        if len(text) + len(answer) > remaining:
            break
        remaining -= len(text) + len(answer)
        result.append({'turn_id': 'turn-{}'.format(turn.pk), 'user_text': text,
                       'assistant_text': answer, 'intent': turn.intent})
    return list(reversed(result))


def replay(user, request_id, request_hash):
    turn = SupportTurn.objects.filter(user=user, request_id=request_id).first()
    if turn is None:
        return None
    if turn.request_hash != request_hash:
        raise ConversationConflict('相同请求 ID 不能用于不同内容')
    return turn.response


@transaction.atomic
def commit_turn(user, conversation, revision, request_id, request_hash, message, response):
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
    current.save(update_fields=['revision', 'updated_at'])
    result = dict(response, conversation_id=str(current.pk), revision=current.revision, request_id=str(request_id))
    SupportTurn.objects.create(conversation=current, user=user, request_id=request_id, request_hash=request_hash,
                               sequence=current.revision, user_text=message, answer=result['answer'],
                               intent=result['intent'], response=result)
    return result
