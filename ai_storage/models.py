import uuid

from django.db import models
from pgvector.django import VectorField


class BuyerMemory(models.Model):
    # MySQL UserProfile is authoritative; Django does not support cross-DB foreign keys.
    owner_id = models.PositiveBigIntegerField(unique=True)
    preferences = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class EmbeddingSpace(models.Model):
    """One key identifies one provider/model/revision/dimension combination."""

    key = models.CharField(max_length=100, unique=True)
    provider = models.CharField(max_length=100)
    model = models.CharField(max_length=200)
    revision = models.CharField(max_length=100)
    dimensions = models.PositiveIntegerField()

    class Meta:
        constraints = [models.CheckConstraint(check=models.Q(dimensions__gt=0), name='ai_dimensions_positive')]


class KnowledgeDocument(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source_key = models.CharField(max_length=200)
    version = models.PositiveIntegerField(default=1)
    title = models.CharField(max_length=255)
    source_reference = models.CharField(max_length=1000, blank=True)
    status = models.CharField(max_length=12, choices=[('draft', 'Draft'), ('published', 'Published'), ('withdrawn', 'Withdrawn')], default='draft')
    visibility = models.CharField(max_length=8, choices=[('public', 'Public'), ('private', 'Private')], default='private')
    owner_id = models.PositiveBigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['source_key', 'version'], name='ai_document_version_unique'),
            models.CheckConstraint(check=models.Q(version__gt=0), name='ai_document_version_positive'),
            models.CheckConstraint(check=models.Q(status__in=['draft', 'published', 'withdrawn']), name='ai_document_status_valid'),
            models.CheckConstraint(check=models.Q(visibility='public') | models.Q(visibility='private', owner_id__isnull=False),
                                   name='ai_document_visibility_valid'),
        ]
        indexes = [models.Index(fields=['status', 'visibility', 'owner_id'], name='ai_document_access_idx')]


class KnowledgeChunk(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='chunks')
    ordinal = models.PositiveIntegerField()
    text = models.TextField()
    metadata = models.JSONField(default=dict)
    # Do not guess the eventual model dimension. Compare/index only a single space.
    embedding = VectorField(null=True, blank=True)
    embedding_space = models.ForeignKey(EmbeddingSpace, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['document', 'ordinal'], name='ai_chunk_ordinal_unique'),
            models.CheckConstraint(check=(models.Q(embedding__isnull=True, embedding_space__isnull=True)
                                          | models.Q(embedding__isnull=False, embedding_space__isnull=False)),
                                   name='ai_chunk_embedding_pair'),
        ]
