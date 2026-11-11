"""Reliable background account-profile processing, outside chat latency."""
from django.db import transaction

from ai_storage.profile_service import (enabled, claim_job, complete_job, fail_job,
                                       enqueue_behavior)
from users.models import UserProfile
from .models import SupportTurn
from .cost_control import CostPolicy, RequestBudget, bind_budget


def process_next(*, model=None, now=None):
    if not enabled():
        return {'status': 'disabled'}
    job = claim_job(now=now)
    if job is None:
        return {'status': 'idle'}
    try:
        if job.source_type == 'chat':
            turn = SupportTurn.objects.filter(pk=job.source_ref, user_id=job.owner_id).first()
            user = UserProfile.objects.filter(pk=job.owner_id, is_active=True, user_type='customer').first()
            from ai_storage.profile_service import _eligible_turn
            if turn is None or user is None or not _eligible_turn(turn):
                return {'status': 'done', 'result': complete_job(job.pk, job.lease_token, [], now=now)}
            from .profile_extraction import extract_candidates
            if model is None:
                from .configuration import effective_configuration
                from .model_client import configured_model
                model = configured_model(effective_configuration(), timeout=15, max_retries=0, max_tokens=768)
            budget = RequestBudget(CostPolicy(1, 16000, 768))
            budget.stage_policy['extraction'] = ('disabled', 768)
            rejections = []
            with bind_budget(budget):
                candidates = extract_candidates(model, turn.user_text, review_callback=rejections.extend)
            return {'status': 'done', 'result': complete_job(job.pk, job.lease_token, candidates,
                                                           now=now, extraction_rejections=rejections)}
        if job.source_type == 'behavior':
            # An order may have changed since queue admission. Re-read live
            # state under the same per-owner serialization as the snapshotter.
            from .profile_behavior import build_behavior_snapshot
            with transaction.atomic():
                user = UserProfile.objects.select_for_update().filter(
                    pk=job.owner_id, is_active=True, user_type='customer').first()
                if user is None:
                    return {'status': 'done', 'result': complete_job(job.pk, job.lease_token, [], now=now)}
                snapshot = build_behavior_snapshot(job.owner_id, now=now)
                if snapshot['fingerprint'] != job.payload['fingerprint']:
                    enqueue_behavior(job.owner_id, snapshot['fingerprint'], snapshot['source_at'],
                                     snapshot['candidates'], evidence=snapshot.get('evidence'))
                    candidates = []  # complete_job rejects the obsolete generation.
                else:
                    candidates = snapshot['candidates']
                return {'status': 'done', 'result': complete_job(job.pk, job.lease_token, candidates, now=now)}
        raise ValueError('Unsupported event kind')
    except Exception:
        # ValidationError details and exception text can contain source input.
        # Persist only this finite operational code, and never retry the chat.
        code = 'MODEL_OR_SCHEMA_FAILURE' if job.source_type == 'chat' else 'BEHAVIOR_SOURCE_FAILURE'
        fail_job(job.pk, job.lease_token, code, now=now)
        return {'status': 'retry_or_dead', 'error_code': code}


def retry_dead_job(job_id, *, now=None):
    """Explicit operator repair only; never automatically regenerate dead jobs."""
    if not enabled():
        return False
    from ai_storage.profile_models import PreferenceUpdateJob
    from django.utils import timezone
    from uuid import UUID
    job_id = UUID(str(job_id))
    with transaction.atomic():
        job = PreferenceUpdateJob.objects.select_for_update().filter(pk=job_id, status='dead').first()
        if job is None:
            return False
        payload = dict(job.payload)
        payload['operator_retry_count'] = int(payload.get('operator_retry_count', 0)) + 1
        payload['operator_prior_attempts'] = int(payload.get('operator_prior_attempts', 0)) + job.attempts
        job.payload = payload
        job.status, job.attempts = 'queued', 0
        job.lease_token = job.lease_until = None
        job.available_at, job.error_code = now or timezone.now(), ''
        job.save()
        return True
