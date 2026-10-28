"""Application-only vector retrieval and local-model query adapter."""

import math
import re
from functools import reduce
from operator import or_

from django.conf import settings
from django.db.models import Q
from django.db import connections
from django.contrib.postgres.search import SearchQuery, SearchRank
from pgvector.django import CosineDistance

from .embeddings import embed_text
from .models import EmbeddingSpace, KnowledgeChunk


def hybrid_search_ready():
    """Safe rollout probe; never query a missing table and poison a transaction."""
    connection = connections['ai_storage']
    if connection.vendor != 'postgresql':
        return False
    with connection.cursor() as cursor:
        cursor.execute('SELECT to_regclass(%s)', ['ai_storage_knowledgerevision'])
        return cursor.fetchone()[0] is not None


def accessible_chunks(owner_id, limit):
    if (owner_id is not None and (type(owner_id) is not int or owner_id <= 0)) or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('invalid trusted owner or result limit')
    rows = KnowledgeChunk.objects.defer('search_text', 'search_vector').filter(document__status='published').select_related('document')
    return rows.filter(Q(document__visibility='public') | Q(document__visibility='private', document__owner_id=owner_id)) if owner_id is not None else rows.filter(document__visibility='public')


def result_row(row, **scores):
    return dict(chunk_id=row.pk, document_id=str(row.document_id), document_version=row.document.version,
                text=row.text, metadata=row.metadata, source_title=row.document.title,
                source_reference=row.document.source_reference, **scores)


def lexical_terms(query):
    """Literal Unicode tokens plus Han bigrams, matching ai_search_terms()."""
    words = re.findall(r'[^\W_]+', query.lower(), re.UNICODE)
    terms = []
    stop = {'the', 'a', 'an', 'is', 'are', 'and', 'or', 'of', 'in', 'to', 'what', 'how'}
    for word in words:
        for part in re.findall(r'[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+', word):
            if re.fullmatch(r'[\u4e00-\u9fff]+', part):
                terms.extend(part[i:i+2] for i in range(max(1, len(part)-1)))
            elif part not in stop:
                terms.append(part)
    return list(dict.fromkeys(terms))[:64]


def search_knowledge_keywords(query, owner_id, limit=15):
    rows = accessible_chunks(owner_id, limit)
    terms = lexical_terms(query)
    if not terms:
        return []
    # plain SearchQuery binds parameters; user text cannot become tsquery syntax.
    expression = reduce(or_, [SearchQuery(term, config='simple', search_type='plain') for term in terms])
    rows = rows.filter(search_vector=expression).annotate(keyword_score=SearchRank('search_vector', expression))
    return [result_row(row, keyword_score=float(row.keyword_score)) for row in rows.order_by('-keyword_score', 'id')[:limit]]


def search_knowledge(embedding, space_key, owner_id, limit=5):
    if (owner_id is not None and (type(owner_id) is not int or owner_id <= 0)) or type(limit) is not int or not 1 <= limit <= 100:
        raise ValueError('invalid trusted owner or result limit')
    space = EmbeddingSpace.objects.get(key=space_key)
    if not isinstance(embedding, (list, tuple)) or len(embedding) != space.dimensions:
        raise ValueError('query dimensions do not match the embedding space')
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in embedding):
        raise ValueError('query vector must contain finite numbers')
    if not any(embedding):
        raise ValueError('cosine search requires a non-zero vector')
    # Publication and trusted owner filters precede ranking; never mix model spaces.
    results = accessible_chunks(owner_id, limit).filter(embedding_space=space, embedding__isnull=False)
    # None explicitly means public-only access, never an anonymous private owner.
    if owner_id is None:
        results = results.filter(document__visibility='public')
    results = results.annotate(distance=CosineDistance('embedding', embedding)).order_by('distance', 'id')[:limit]
    return [{'chunk_id': row.pk, 'document_id': str(row.document_id), 'document_version': row.document.version, 'text': row.text,
             'distance': float(row.distance), 'metadata': row.metadata,
             'source_title': row.document.title, 'source_reference': row.document.source_reference}
            for row in results]


def search_knowledge_text(query, owner_id, limit=5):
    """Embed a user query with the configured local model, then retrieve its evidence."""
    return search_knowledge(embed_text(query), settings.AI_EMBEDDING_SPACE_KEY, owner_id, limit=limit)
