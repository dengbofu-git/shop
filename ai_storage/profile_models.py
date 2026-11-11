"""Application-owned preference state and durable post-commit work."""
import uuid

from django.db import models
from django.utils import timezone


class BuyerPreferenceState(models.Model):
    owner_id = models.PositiveBigIntegerField(unique=True)
    revision = models.PositiveBigIntegerField(default=0)
    reset_at = models.DateTimeField(null=True, blank=True)
    # A submitted list replaces that field, including terms not yet extracted.
    field_fences = models.JSONField(default=dict)
    records = models.JSONField(default=dict)
    projection_hash = models.CharField(max_length=64, blank=True)
    behavior_generation = models.PositiveBigIntegerField(default=0)
    behavior_applied_generation = models.PositiveBigIntegerField(default=0)
    behavior_fingerprint = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class PreferenceUpdateJob(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    event_key = models.CharField(max_length=200, unique=True)
    owner_id = models.PositiveBigIntegerField()
    source_type = models.CharField(max_length=12, choices=[('chat', 'chat'), ('behavior', 'behavior')])
    source_ref = models.CharField(max_length=200)
    source_at = models.DateTimeField(null=True, blank=True)
    payload = models.JSONField(default=dict)
    results = models.JSONField(default=dict)
    status = models.CharField(max_length=12, default='queued', choices=[(s, s) for s in ('queued', 'running', 'done', 'dead')])
    attempts = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    available_at = models.DateTimeField(default=timezone.now)
    error_code = models.CharField(max_length=60, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'available_at', 'lease_until'], name='ai_profile_job_ready')]
        constraints = [
            models.CheckConstraint(condition=models.Q(source_type__in=['chat', 'behavior']), name='ai_profile_job_source'),
            models.CheckConstraint(condition=models.Q(status__in=['queued', 'running', 'done', 'dead']), name='ai_profile_job_status'),
        ]


class PreferenceAudit(models.Model):
    owner_id = models.PositiveBigIntegerField()
    source_type = models.CharField(max_length=12)
    source_ref = models.CharField(max_length=200)
    source_at = models.DateTimeField(null=True, blank=True)
    record_key = models.CharField(max_length=80, blank=True)
    outcome = models.CharField(max_length=12)
    reason = models.CharField(max_length=60)
    candidate = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=['owner_id', 'created_at'], name='ai_profile_owner_trace')]
