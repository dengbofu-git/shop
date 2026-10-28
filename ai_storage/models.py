import uuid

from django.db import models
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
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
    # Derived by PostgreSQL triggers; text remains the immutable citation source.
    search_text = models.TextField(default='', editable=False)
    search_vector = SearchVectorField(null=True, editable=False)
    metadata = models.JSONField(default=dict)
    # Do not guess the eventual model dimension. Compare/index only a single space.
    embedding = VectorField(null=True, blank=True)
    embedding_space = models.ForeignKey(EmbeddingSpace, on_delete=models.PROTECT, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [GinIndex(fields=['search_vector'], name='ai_chunk_search_gin')]
        constraints = [
            models.UniqueConstraint(fields=['document', 'ordinal'], name='ai_chunk_ordinal_unique'),
            models.CheckConstraint(check=(models.Q(embedding__isnull=True, embedding_space__isnull=True)
                                          | models.Q(embedding__isnull=False, embedding_space__isnull=False)),
                                   name='ai_chunk_embedding_pair'),
        ]


class KnowledgeRevision(models.Model):
    """Transactional invalidation epoch, maintained even for bulk/SQL writes."""
    revision = models.PositiveBigIntegerField(default=1)


class KnowledgeImportJob(models.Model):
    """Application-owned pipeline; PostgreSQL references MySQL identities by ID."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    document = models.OneToOneField(KnowledgeDocument, on_delete=models.PROTECT, related_name='pdf_import')
    actor_id = models.PositiveBigIntegerField()
    fingerprint = models.CharField(max_length=64, unique=True)
    file_sha256 = models.CharField(max_length=64)
    config = models.JSONField(default=dict)
    status = models.CharField(max_length=24, default='queued', choices=[
        (s, s) for s in ('queued', 'running', 'awaiting_review', 'succeeded', 'failed', 'cancelled')])
    stage = models.CharField(max_length=24, default='queued')
    total_pages = models.PositiveIntegerField(default=0)
    processed_pages = models.PositiveIntegerField(default=0)
    attempt = models.PositiveIntegerField(default=0)
    error_code = models.CharField(max_length=60, blank=True)
    warnings = models.JSONField(default=list)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_until = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.PositiveBigIntegerField(null=True, blank=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [models.Index(fields=['status', 'lease_until'], name='ai_import_queue_idx')]


class KnowledgePage(models.Model):
    document = models.ForeignKey(KnowledgeDocument, on_delete=models.CASCADE, related_name='pages')
    number = models.PositiveIntegerField()
    status = models.CharField(max_length=12, default='pending')
    method = models.CharField(max_length=16, blank=True)
    width = models.FloatField(default=0)
    height = models.FloatField(default=0)
    rotation = models.PositiveSmallIntegerField(default=0)
    blocks = models.JSONField(default=list)
    warnings = models.JSONField(default=list)
    error_code = models.CharField(max_length=60, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['document', 'number'], name='ai_page_number_unique')]
        ordering = ['number']
