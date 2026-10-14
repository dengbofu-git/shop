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
