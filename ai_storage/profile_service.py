"""Account profile updates; provenance and write authority stay in Python."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone as dt_timezone
import hashlib
import json
import math
import re
import unicodedata
import uuid

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import connections, transaction
from django.db.models import Q
from django.utils import timezone

from .database import alias
from .models import BuyerMemory
from .profile_models import BuyerPreferenceState, PreferenceAudit, PreferenceUpdateJob

FIELDS = {'category': 'categories', 'brand': 'brands', 'keyword': 'keywords'}
ALL_FIELDS = tuple(FIELDS.values()) + tuple('disliked_' + x for x in FIELDS.values())
MAX_RECORDS = 500
MAX_ATTEMPTS = 5
EXTRACTION_REJECTION_CODES = frozenset({
    'current_turn', 'quote_not_verbatim', 'value_not_in_quote',
    'unsupported_or_inverted_polarity', 'temporary_ambiguous_or_context_mismatch',
    'conflicting_candidates', 'duplicate_candidate',
})


def enabled():
    return bool(getattr(settings, 'SUPPORT_AUTO_PROFILE_ENABLED', False))


def _db():
    if alias() != 'default':
        raise ImproperlyConfigured('Automatic preferences require the unified default transaction connection')
    return 'default'


def _time(value):
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if not isinstance(value, datetime) or timezone.is_naive(value):
        raise ValueError('source_time_invalid')
    return value.astimezone(dt_timezone.utc)


def _term(value):
    from support_ai.pii import contains_pii
    if not isinstance(value, str):
        raise ValueError('term_invalid')
    value = ' '.join(unicodedata.normalize('NFKC', value).split())
    if not 1 <= len(value) <= 40 or contains_pii(value) or any(ord(x) < 32 for x in value):
        raise ValueError('term_invalid')
    return value


def _key(kind, value):
    from support_ai.profile_contracts import normalized_key
    return normalized_key(kind, value)


def _audit(owner_id, source_type, source_ref, source_at, key, outcome, reason, candidate=None):
    PreferenceAudit.objects.using(_db()).create(owner_id=owner_id, source_type=source_type,
        source_ref=source_ref, source_at=source_at, record_key=key, outcome=outcome, reason=reason,
        candidate=candidate or {})


def _lock_state(owner_id):
    from users.models import UserProfile
    # Every entry point uses this same existing row before creating profile rows.
    UserProfile.objects.using(_db()).select_for_update().get(pk=owner_id)
    state, created = BuyerPreferenceState.objects.using(_db()).select_for_update().get_or_create(owner_id=owner_id)
    memory = BuyerMemory.objects.using(_db()).select_for_update().filter(owner_id=owner_id).first()
    if created and memory:
        records = {}
        for kind, field in FIELDS.items():
            for polarity, name in [('like', field), ('hate', 'disliked_' + field)]:
                for value in memory.preferences.get(name, []):
                    value = _term(value)
                    records[_key(kind, value)] = dict(type=kind, value=value, polarity=polarity,
                        source_type='manual', source_ref='legacy:' + str(memory.pk),
                        source_at=memory.updated_at.isoformat(), weight=1.0)
        state.records = records
        state.field_fences = {name:memory.updated_at.isoformat() for name in ALL_FIELDS
                              if name in memory.preferences}
        # Early stale/missing-source returns must not leave an empty state row
        # hiding the existing legacy projection from subsequent readers.
        state.save(using=_db(), update_fields=['records','field_fences','updated_at'])
    return state, memory


def _project(records, now):
    values = {field: [] for field in ALL_FIELDS}
    ranked = []
    for key, record in records.items():
        if record['polarity'] == 'neutral':
            continue
        score = float(record.get('weight', 1.0))
        if record['source_type'] == 'behavior':
            days = max(0.0, (now - _time(record['source_at'])).total_seconds() / 86400)
            score *= 2 ** (-days / 90)
            if score < .5:
                continue
        priority = 1 if record['source_type'] == 'behavior' else 2
        ranked.append((-priority, -score, -_time(record['source_at']).timestamp(), key, record))
    for _, _, _, _, record in sorted(ranked):
        field = FIELDS[record['type']]
        if record['polarity'] == 'hate':
            field = 'disliked_' + field
        if len(values[field]) < 5:
            values[field].append(record['value'])
    return values


def _save(state, now):
    values = _project(state.records, now)
    state.revision += 1
    state.projection_hash = hashlib.sha256(json.dumps(values, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    state.save(using=_db())
    if any(values.values()):
        BuyerMemory.objects.using(_db()).update_or_create(owner_id=state.owner_id, defaults={'preferences': values})
    else:
        # Public DELETE semantics remove the active memory row. Durable fences
        # remain in the separate state and cannot be undone by delayed work.
        BuyerMemory.objects.using(_db()).filter(owner_id=state.owner_id).delete()
    return values


def read_preferences(user, now=None):
    """The saved-preferences DTO; aging changes a soft projection, never facts."""
    memory = BuyerMemory.objects.using(_db()).filter(owner_id=user.pk).first()
    if memory is None:
        return None
    state = BuyerPreferenceState.objects.using(_db()).filter(owner_id=user.pk).first()
    if state is None:
        values = {name: list(memory.preferences.get(name, [])) for name in ALL_FIELDS}
        marker = memory.updated_at.isoformat()
    else:
        values = _project(state.records, _time(now or timezone.now()))
        marker = str(state.revision)
    if not any(values.values()):
        return None
    return {'id': f'preference:{memory.pk}:{marker}', 'preferences': values}


def manual_preferences(user, values=None, delete=False):
    values = {} if values is None else values
    if not isinstance(values, dict) or set(values) - set(ALL_FIELDS):
        raise ValueError('preference_fields_invalid')
    cleaned = {}
    for field, terms in values.items():
        if not isinstance(terms, list) or len(terms) > 5:
            raise ValueError('preference_values_invalid')
        cleaned[field] = list(dict.fromkeys(_term(x) for x in terms))
    for field in FIELDS.values():
        if {x.casefold() for x in cleaned.get(field, [])} & {x.casefold() for x in cleaned.get('disliked_' + field, [])}:
            raise ValueError('preference_polarity_conflict')
    with transaction.atomic(using=_db()):
        state, _ = _lock_state(user.pk)
        now = timezone.now()
        records = deepcopy(state.records)
        source_ref = 'manual:' + uuid.uuid4().hex
        for key, record in list(records.items()):
            field = FIELDS[record['type']]
            if record['polarity'] == 'hate':
                field = 'disliked_' + field
            retain = {x.casefold() for x in cleaned.get(field, [])}
            if delete or (field in cleaned and record['value'].casefold() not in retain):
                records[key] = dict(type=record['type'], value=record['value'], polarity='neutral',
                    source_type='manual', source_ref=source_ref, source_at=now.isoformat(), weight=0)
                _audit(user.pk, 'manual', source_ref, now, key, 'applied', 'manual_removed')
        if delete:
            state.reset_at = now
        else:
            state.field_fences = dict(state.field_fences, **{name:now.isoformat() for name in cleaned})
            for kind, field in FIELDS.items():
                for polarity, name in [('like', field), ('hate', 'disliked_' + field)]:
                    for value in cleaned.get(name, []):
                        key = _key(kind, value)
                        if key not in records and len(records) >= MAX_RECORDS:
                            raise ValueError('profile_capacity')
                        records[key] = dict(type=kind, value=value, polarity=polarity,
                            source_type='manual', source_ref=source_ref, source_at=now.isoformat(), weight=1.0)
                        _audit(user.pk, 'manual', source_ref, now, key, 'applied', 'manual_saved')
        state.records = records
        return _save(state, now)


def _eligible_turn(turn):
    response = turn.response
    if not isinstance(response, dict) or response.get('compliance_blocked') or response.get('error'):
        return False
    if response.get('completion_status') == 'partial':
        return False
    return not any(isinstance(t, dict) and t.get('status') in ('failed', 'failure', 'error', 'technical_failure', 'skipped')
                   for t in response.get('tasks', []))


def enqueue_chat(turn, source_at=None):
    if not enabled() or not getattr(settings, 'SUPPORT_PROFILE_CHAT_ENABLED', True):
        return None
    if not connections[_db()].in_atomic_block:
        raise RuntimeError('Chat outbox must be written inside commit_turn transaction')
    from support_ai.models import SupportTurn
    saved = SupportTurn.objects.using(_db()).filter(pk=turn.pk, user_id=turn.user_id).first()
    if saved is None or not _eligible_turn(saved):
        return None
    source_at = _time(saved.created_at if source_at is None else source_at)
    if source_at > saved.created_at or source_at > timezone.now():
        raise ValueError('chat_event_time_invalid')
    row, _ = PreferenceUpdateJob.objects.using(_db()).get_or_create(event_key=f'chat:{saved.pk}', defaults={
        'owner_id': saved.user_id, 'source_type': 'chat', 'source_ref': str(saved.pk),
        'source_at': source_at, 'payload': {}})
    return row


def enqueue_behavior(owner_id, fingerprint, source_at, candidates, evidence=None):
    if not enabled() or not getattr(settings, 'SUPPORT_PROFILE_BEHAVIOR_ENABLED', True):
        return None
    if not isinstance(fingerprint, str) or not re.fullmatch(r'[0-9a-f]{64}', fingerprint):
        raise ValueError('fingerprint_invalid')
    if not isinstance(candidates, list) or len(candidates) > 300:
        raise ValueError('candidates_invalid')
    source_at = _time(source_at) if source_at is not None else None
    with transaction.atomic(using=_db()):
        state, _ = _lock_state(owner_id)
        if state.behavior_fingerprint == fingerprint:
            return None
        state.behavior_generation += 1
        state.behavior_fingerprint = fingerprint
        state.save(using=_db())
        key = f'behavior:{owner_id}:{state.behavior_generation}:{fingerprint}'
        return PreferenceUpdateJob.objects.using(_db()).create(event_key=key, owner_id=owner_id,
            source_type='behavior', source_ref=key, source_at=source_at,
            payload={'generation':state.behavior_generation, 'fingerprint':fingerprint,
                     'candidates':candidates, 'evidence':evidence or {}})


def _source_turn(owner_id, source_ref):
    from support_ai.models import SupportTurn
    if not isinstance(source_ref, str) or not re.fullmatch(r'\d{1,20}', source_ref):
        return None
    turn = SupportTurn.objects.using(_db()).filter(pk=int(source_ref), user_id=owner_id).first()
    return turn if turn and _eligible_turn(turn) else None


def _chat_source_time(turn):
    """Only application admission metadata can precede the commit timestamp."""
    event = PreferenceUpdateJob.objects.using(_db()).filter(event_key=f'chat:{turn.pk}').first()
    if event is None:
        return turn.created_at  # Legacy direct calls did not have an outbox event.
    if (event.source_type != 'chat' or event.owner_id != turn.user_id
            or event.source_ref != str(turn.pk)):
        raise ValueError('chat_event_binding_invalid')
    try:
        occurred = _time(event.source_at)
    except ValueError as exc:
        raise ValueError('chat_event_time_invalid') from exc
    if occurred > turn.created_at or occurred > timezone.now():
        raise ValueError('chat_event_time_invalid')
    return occurred


def _candidate(candidate, source_type, source_at, turn):
    if not isinstance(candidate, dict) or candidate.get('type') not in FIELDS:
        raise ValueError('candidate_type_invalid')
    if candidate.get('scope') != 'long_term':
        raise ValueError('not_long_term')
    polarity = candidate.get('polarity')
    if polarity not in ('like', 'hate') or (source_type == 'behavior' and polarity != 'like'):
        raise ValueError('candidate_polarity_invalid')
    value = _term(candidate.get('value'))
    quote = candidate.get('quote', '')
    evidence = candidate.get('evidence', {})
    if source_type == 'chat':
        if (turn is None or not isinstance(quote, str) or not 1 <= len(quote) <= 300
                or quote not in turn.user_text or value.casefold() not in
                ' '.join(unicodedata.normalize('NFKC', quote).split()).casefold()):
            raise ValueError('quote_source_invalid')
        weight = 1.0
        evidence = {}
    else:
        if quote or not isinstance(evidence, dict):
            raise ValueError('behavior_evidence_invalid')
        source_at = _time(candidate.get('source_at') or source_at)
        weight = candidate.get('weight', 0)
        if type(weight) not in (float, int) or not math.isfinite(weight) or not 0 <= weight <= 5:
            raise ValueError('behavior_weight_invalid')
    return _key(candidate['type'], value), dict(type=candidate['type'], value=value, polarity=polarity,
        source_at=_time(source_at).isoformat(), weight=weight, quote=quote, evidence=evidence)


def _apply(owner_id, candidates, source_type, source_ref, source_at, now, *, behavior_generation=None):
    state, _ = _lock_state(owner_id)
    results = {'applied':0, 'ignored':0, 'rejected':0, 'reasons':[]}
    if source_type == 'behavior' and behavior_generation != state.behavior_generation:
        return dict(results, stale=True, reasons=['stale_behavior_generation'])
    turn = _source_turn(owner_id, source_ref) if source_type == 'chat' else None
    if source_type == 'chat' and turn is None:
        return dict(results, rejected=len(candidates), reasons=['chat_source_unavailable'])
    if source_type == 'chat':
        try:
            source_at = _chat_source_time(turn)
        except ValueError as exc:
            return dict(results, rejected=len(candidates), reasons=[str(exc)])
    prepared = []
    for candidate in candidates:
        try:
            key, record = _candidate(candidate, source_type, source_at, turn)
            prepared.append((key, record))
        except (ValueError, TypeError, OverflowError) as exc:
            reason = str(exc) if str(exc) in {'candidate_type_invalid','not_long_term','candidate_polarity_invalid',
                'term_invalid','quote_source_invalid','behavior_evidence_invalid','behavior_weight_invalid','source_time_invalid'} else 'candidate_invalid'
            _audit(owner_id, source_type, source_ref, source_at, '', 'rejected', reason)
            results['rejected'] += 1
            results['reasons'].append(reason)
    records = deepcopy(state.records)
    if source_type == 'behavior':
        # An authoritative snapshot can remove only its own weak contributions.
        records = {key: r for key,r in records.items() if r['source_type'] != 'behavior'}
        state.behavior_applied_generation = behavior_generation
    polarities = {}
    for key, record in prepared:
        polarities.setdefault(key,set()).add(record['polarity'])
    for key, record in prepared:
        reason = None
        occurred = _time(record['source_at'])
        existing = records.get(key)
        field = FIELDS[record['type']]
        if record['polarity'] == 'hate':
            field = 'disliked_' + field
        field_fence = state.field_fences.get(field)
        if len(polarities[key]) > 1:
            reason = 'conflicting_batch_candidates'
        elif occurred > now + timedelta(seconds=1):
            reason = 'future_source_time'
        elif state.reset_at and occurred <= state.reset_at:
            reason = 'before_manual_reset'
        elif field_fence and occurred <= _time(field_fence):
            reason = 'before_manual_field_update'
        elif existing and source_type == 'behavior' and existing['source_type'] != 'behavior':
            reason = 'explicit_preference_wins'
        elif existing and source_type == 'chat' and existing['source_type'] != 'behavior':
            old_order = (_time(existing['source_at']), existing['source_type'] == 'manual',
                         int(existing['source_ref']) if existing['source_type']=='chat' else 0)
            new_order = (occurred, False, int(source_ref))
            if new_order <= old_order:
                reason = 'older_or_duplicate_explicit_source'
        elif key not in records and len(records) >= MAX_RECORDS:
            reason = 'profile_capacity'
        if reason:
            _audit(owner_id, source_type, source_ref, occurred, key, 'ignored', reason)
            results['ignored'] += 1
            results['reasons'].append(reason)
            continue
        record.update(source_type=source_type, source_ref=source_ref)
        records[key] = record
        _audit(owner_id, source_type, source_ref, occurred, key, 'applied', 'accepted', record)
        results['applied'] += 1
    state.records = records
    results['preferences'] = _save(state, now)
    return results


def apply_candidates(owner_id, candidates, source_type, source_ref, source_at, now=None, *, behavior_generation=None):
    if source_type not in ('chat','behavior') or not isinstance(candidates,list) or len(candidates)>300:
        raise ValueError('candidate_batch_invalid')
    with transaction.atomic(using=_db()):
        return _apply(owner_id, candidates, source_type, source_ref, source_at,
                      _time(now or timezone.now()), behavior_generation=behavior_generation)


def claim_job(now=None, lease_seconds=120):
    if not enabled():
        return None
    now = _time(now or timezone.now())
    with transaction.atomic(using=_db()):
        qs = PreferenceUpdateJob.objects.using(_db()).filter(available_at__lte=now).filter(
            Q(status='queued') | Q(status='running', lease_until__lte=now))
        # Expired final-attempt work is terminal, never stranded as running.
        qs.filter(attempts__gte=MAX_ATTEMPTS).update(status='dead',error_code='attempts_exhausted',lease_token=None,lease_until=None)
        job = qs.filter(attempts__lt=MAX_ATTEMPTS).select_for_update(skip_locked=True).order_by('available_at','created_at','id').first()
        if job is None:
            return None
        job.status = 'running'
        job.attempts += 1
        job.lease_token = uuid.uuid4()
        job.lease_until = now + timedelta(seconds=max(10,min(int(lease_seconds),600)))
        job.save(using=_db())
        return job


def _extraction_rejections(value):
    if value is None:
        return []
    if not isinstance(value,list) or len(value)>6:
        raise ValueError('extraction_audit_invalid')
    cleaned, seen = [], set()
    for item in value:
        if (type(item) is not dict or set(item) != {'index','reason'}
                or type(item['index']) is not int or not 0 <= item['index'] <= 5
                or type(item['reason']) is not str or item['reason'] not in EXTRACTION_REJECTION_CODES
                or item['index'] in seen):
            raise ValueError('extraction_audit_invalid')
        seen.add(item['index'])
        cleaned.append(dict(item))
    return sorted(cleaned,key=lambda item:item['index'])


def complete_job(job_id, lease_token, candidates, now=None, *, extraction_rejections=None):
    extraction_rejections = _extraction_rejections(extraction_rejections)
    if not enabled():
        return {'stale':True,'reasons':['automatic_updates_disabled']}
    now = _time(now or timezone.now())
    with transaction.atomic(using=_db()):
        job = PreferenceUpdateJob.objects.using(_db()).select_for_update().get(pk=job_id)
        if job.status != 'running' or job.lease_token != lease_token or not job.lease_until or job.lease_until <= now:
            return {'stale':True,'reasons':['lease_unavailable']}
        if not isinstance(candidates,list) or len(candidates)>300:
            raise ValueError('candidate_batch_invalid')
        from users.models import UserProfile
        owner = UserProfile.objects.using(_db()).select_for_update().filter(pk=job.owner_id).first()
        binding_invalid = False
        if job.source_type == 'chat':
            binding_invalid = (not re.fullmatch(r'[1-9]\d{0,19}',job.source_ref)
                               or job.event_key != 'chat:' + job.source_ref)
            if not binding_invalid:
                from support_ai.models import SupportTurn
                actual_owner = SupportTurn.objects.using(_db()).filter(pk=int(job.source_ref)).values_list('user_id',flat=True).first()
                binding_invalid = actual_owner is not None and actual_owner != job.owner_id
        if owner is None or not owner.is_active or owner.user_type != 'customer':
            # Account validity can change while a worker is calling a model.
            # Complete this event rather than retrying it or creating a profile.
            result = {'applied':0,'ignored':max(1,len(candidates)),'rejected':0,
                      'reasons':['account_unavailable']}
        elif binding_invalid:
            result = {'applied':0,'ignored':0,'rejected':max(1,len(candidates)),
                      'reasons':['chat_event_binding_invalid']}
        else:
            result = _apply(job.owner_id, candidates, job.source_type, job.source_ref, job.source_at, now,
                            behavior_generation=job.payload.get('generation') if job.source_type=='behavior' else None)
        result['extraction_rejections'] = extraction_rejections
        job.status = 'done'
        job.results = result
        job.lease_token = job.lease_until = None
        job.error_code = ''
        job.save(using=_db())
        return result


finish_job = complete_job


def fail_job(job_id, lease_token, error_code, now=None):
    now = _time(now or timezone.now())
    if not isinstance(error_code,str) or not re.fullmatch(r'[A-Z][A-Z0-9_]{0,59}', error_code):
        error_code = 'PROFILE_PROCESSING_FAILED'
    with transaction.atomic(using=_db()):
        job = PreferenceUpdateJob.objects.using(_db()).select_for_update().get(pk=job_id)
        if job.status != 'running' or job.lease_token != lease_token or not job.lease_until or job.lease_until <= now:
            return False
        job.status = 'dead' if job.attempts >= MAX_ATTEMPTS else 'queued'
        job.available_at = now + timedelta(seconds=min(1800,30*2**(job.attempts-1)))
        job.error_code = error_code
        job.lease_token = job.lease_until = None
        job.save(using=_db())
        return True
