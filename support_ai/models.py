import uuid

from django.db import models


class SupportPreference(models.Model):
    """Legacy MySQL preferences, retained only for non-destructive transfer to PostgreSQL."""

    user = models.OneToOneField('users.UserProfile', on_delete=models.CASCADE)
    preferences = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)


class SupportConversation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE)
    revision = models.PositiveIntegerField(default=0)
    # Application-only reference; never serialize the real order ID into Agent input.
    active_order_id = models.CharField(max_length=64, blank=True, default='')
    active_order_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class SupportTurn(models.Model):
    conversation = models.ForeignKey(SupportConversation, on_delete=models.CASCADE, related_name='turns')
    user = models.ForeignKey('users.UserProfile', on_delete=models.CASCADE)
    request_id = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    sequence = models.PositiveIntegerField()
    user_text = models.CharField(max_length=1000)
    answer = models.TextField()
    intent = models.CharField(max_length=30)
    response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['user', 'request_id'], name='support_request_unique'),
            models.UniqueConstraint(fields=['conversation', 'sequence'], name='support_sequence_unique'),
        ]


class AgentConfiguration(models.Model):
    """Singleton runtime overrides. Credentials remain in server environment variables."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    model = models.CharField(max_length=100, blank=True)
    thinking = models.CharField(max_length=10, default='inherit')
    telemetry_enabled = models.BooleanField(default=True)
    export_enabled = models.BooleanField(default=False)
    otlp_endpoint = models.URLField(default='http://127.0.0.1:4318')
    rerank_enabled = models.BooleanField(default=False)
    rerank_model = models.CharField(max_length=100, default='BAAI/bge-reranker-v2-m3')
    retrieval_candidates = models.PositiveSmallIntegerField(default=30)
    retrieval_top_k = models.PositiveSmallIntegerField(default=5)
    retrieval_per_document = models.PositiveSmallIntegerField(default=2)
    retrieval_context_chars = models.PositiveIntegerField(default=12000)
    rerank_timeout_ms = models.PositiveIntegerField(default=5000)
    rerank_min_score = models.FloatField(null=True, blank=True)
    rerank_fallback = models.BooleanField(default=True)
    revision = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(id=1), name='support_agent_singleton')]


class AgentConfigurationChange(models.Model):
    operator = models.ForeignKey('users.UserProfile', on_delete=models.SET_NULL, null=True)
    before = models.JSONField()
    after = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)


class AgentSpan(models.Model):
    """Privacy-filtered projection of completed OpenTelemetry spans for the operator UI."""

    trace_id = models.CharField(max_length=32, db_index=True)
    span_id = models.CharField(max_length=16, unique=True)
    parent_span_id = models.CharField(max_length=16, blank=True)
    name = models.CharField(max_length=100)
    started_at = models.DateTimeField(db_index=True)
    duration_ms = models.FloatField()
    status = models.CharField(max_length=10)
    attributes = models.JSONField(default=dict)

    class Meta:
        indexes = [models.Index(fields=['name', 'started_at'], name='support_span_name_time')]
