"""Application-only vector retrieval. Embeddings are supplied by a future ingestion/query adapter."""

import math

from django.db.models import Q
from pgvector.django import CosineDistance

from .models import EmbeddingSpace, KnowledgeChunk


def search_knowledge(embedding, space_key, owner_id, limit=5):
    if type(owner_id) is not int or owner_id <= 0 or type(limit) is not int or not 1 <= limit <= 20:
        raise ValueError('invalid trusted owner or result limit')
    space = EmbeddingSpace.objects.get(key=space_key)
    if not isinstance(embedding, (list, tuple)) or len(embedding) != space.dimensions:
        raise ValueError('query dimensions do not match the embedding space')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in embedding):
        raise ValueError('query vector must contain finite numbers')
    if not any(embedding):
        raise ValueError('cosine search requires a non-zero vector')
    # Publication and trusted owner filters precede ranking; never mix model spaces.
    results = KnowledgeChunk.objects.filter(
        document__status='published', embedding_space=space, embedding__isnull=False,
    ).filter(Q(document__visibility='public') | Q(document__visibility='private', document__owner_id=owner_id))
    results = results.annotate(distance=CosineDistance('embedding', embedding)).order_by('distance', 'id')[:limit]
    return [{'chunk_id': row.pk, 'document_id': str(row.document_id), 'text': row.text,
             'distance': float(row.distance), 'metadata': row.metadata} for row in results]
