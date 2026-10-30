"""Bounded caches: embeddings by model; evidence by database epoch and ACL."""
import hashlib
import json
import math
from copy import deepcopy
from dataclasses import asdict, is_dataclass

from django.conf import settings
from django.core.cache import cache
from django.db import connections

from ai_storage.models import KnowledgeRevision
from ai_storage.knowledge import hybrid_search_ready
from .telemetry import agent_span


def cache_key(kind, value):
    return 'support-rag-v1:{}:{}'.format(kind, hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode('utf8')).hexdigest())


def read(key):
    if key is None:
        return None
    try:
        return deepcopy(cache.get(key))
    except Exception:
        return None


def write(key, value):
    if key is None:
        return
    try:
        ttl = max(0, min(3600, int(getattr(settings, 'SUPPORT_RAG_CACHE_TTL', 300))))
        if ttl:
            cache.set(key, deepcopy(value), timeout=ttl)
    except Exception:
        pass  # A cache outage cannot change tool availability.


def evidence_key(query, owner_id, config, policy):
    connection = connections['ai_storage']
    if (connection.vendor != 'postgresql' or connection.in_atomic_block
            or not getattr(settings, 'SUPPORT_RAG_CACHE_ENABLED', True)):
        return None
    if not hybrid_search_ready():
        return None
    # Do not catch DB errors and serve stale data. Epoch lookup is mandatory.
    epoch = KnowledgeRevision.objects.using('ai_storage').get(pk=1).revision
    database = connection.settings_dict
    return cache_key('evidence', [query, owner_id, epoch,
        [database.get(k) for k in ('HOST', 'PORT', 'NAME')],
        asdict(config) if is_dataclass(config) else vars(config), asdict(policy),
        settings.AI_EMBEDDING_SPACE_KEY, settings.AI_OLLAMA_MODEL, settings.AI_OLLAMA_REVISION,
        settings.AI_RERANK_REVISION, getattr(settings, 'SUPPORT_RAG_HYBRID_ENABLED', True),
        getattr(settings, 'SUPPORT_RAG_RERANK_CANDIDATES', 20)])


def cached_embedding(query, embedder, timeout):
    enabled = getattr(settings, 'SUPPORT_RAG_CACHE_ENABLED', True)
    key = cache_key('embedding', [query, settings.AI_OLLAMA_BASE_URL, settings.AI_OLLAMA_MODEL,
                                  settings.AI_OLLAMA_REVISION, settings.AI_EMBEDDING_SPACE_KEY]) if enabled else None
    with agent_span('knowledge.cache', {'agent.cache.kind':'embedding'}) as span:
        vector = read(key)
        if span:
            span.set_attribute('agent.cache.status', 'hit' if vector is not None else 'miss' if key else 'disabled')
    if vector is not None:
        return vector
    with agent_span('knowledge.embedding'):
        vector = embedder(query, timeout=timeout)
    if (isinstance(vector, list) and vector and any(vector)
            and all(type(x) in (int, float) and math.isfinite(x) for x in vector)):
        write(key, vector)
    return vector
