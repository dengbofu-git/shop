"""Permission-filtered recall, local reranking and bounded evidence selection."""
import hashlib
import logging
import time
from dataclasses import replace

from django.conf import settings

from ai_storage.embeddings import embed_text
from ai_storage.knowledge import search_knowledge
from ai_storage.reranking import RerankUnavailable, rerank_candidates
from .telemetry import agent_span, retrieval_hits, rerank_observation

logger = logging.getLogger(__name__)


def retrieve_scoped_knowledge(query, owner_id, config, category, scope):
    """Share one request's candidate/character budget across its tea queries."""
    from .recommendation_options import BASIC_TEA_TYPES
    if (not scope or len(scope) > 6 or len(set(scope)) != len(scope)
            or any(c not in BASIC_TEA_TYPES for c in scope) or category not in scope):
        raise ValueError('Invalid trusted retrieval scope')
    index, size = scope.index(category), len(scope)
    candidates = config.retrieval_candidates // size + (index < config.retrieval_candidates % size)
    if not candidates:
        return []
    top_k = min(2, config.retrieval_top_k, candidates)
    scoped = replace(config, retrieval_candidates=candidates, retrieval_top_k=top_k,
                     retrieval_per_document=min(config.retrieval_per_document, top_k),
                     retrieval_context_chars=max(200, config.retrieval_context_chars // size))
    return retrieve_knowledge(query, owner_id, scoped)


def deduplicate(candidates):
    seen, unique = set(), []
    for item in candidates:
        digest = hashlib.sha256(' '.join(item['text'].split()).encode('utf-8')).digest()
        if digest not in seen:
            unique.append(item)
            seen.add(digest)
    return unique


def select_evidence(candidates, config):
    selected, deferred, counts = [], [], {}
    for item in candidates:
        if config.rerank_min_score is not None and 'rerank_score' in item and item['rerank_score'] < config.rerank_min_score:
            continue
        key = item['document_id']
        if counts.get(key, 0) >= config.retrieval_per_document:
            deferred.append(item)
        else:
            selected.append(item)
            counts[key] = counts.get(key, 0) + 1
    selected = (selected[:config.retrieval_top_k] + deferred)[:config.retrieval_top_k]
    result, remaining = [], config.retrieval_context_chars
    for item in selected:
        text = item.get('evidence_excerpt', item['text'])
        if len(text) > remaining:
            # Never send an unmarked partial passage as if it were the entire chunk.
            if remaining < 200:
                break
            text = text[:remaining]
            truncated = True
        else:
            truncated = False
        evidence = dict(item, text=text, context_truncated=truncated)
        evidence.pop('evidence_excerpt', None)
        result.append(evidence)
        remaining -= len(text)
    return result


def retrieve_knowledge(query, owner_id, config):
    try:
        with agent_span('knowledge.retrieve') as span:
            with agent_span('embedding.bge-m3'):
                embedding = embed_text(query)
            with agent_span('knowledge.vector_search'):
                candidates = search_knowledge(embedding, settings.AI_EMBEDDING_SPACE_KEY, owner_id,
                                             limit=config.retrieval_candidates if config.rerank_enabled else config.retrieval_top_k)
            candidates = deduplicate([dict(item, vector_rank=i + 1) for i, item in enumerate(candidates)])
            if config.rerank_enabled and candidates:
                started, status, reason = time.perf_counter(), 'success', ''
                ranked = []
                try:
                    with agent_span('knowledge.rerank', {'agent.rerank.model': config.rerank_model,
                                    'agent.rerank.revision': settings.AI_RERANK_REVISION,
                                    'agent.rerank.candidates': len(candidates),
                                    'agent.rerank.input_ids': tuple(str(c['chunk_id']) for c in candidates)}) as rank_span:
                        try:
                            ranked = rerank_candidates(query, candidates, config)
                        except RerankUnavailable as exc:
                            if rank_span:
                                rank_span.set_attribute('agent.rerank.reason', exc.reason)
                            raise
                        if rank_span:
                            rank_span.set_attribute('agent.rerank.output_ids', tuple(str(c['chunk_id']) for c in ranked))
                            rank_span.set_attribute('agent.rerank.scores', tuple(c['rerank_score'] for c in ranked))
                except RerankUnavailable as exc:
                    status = 'fallback' if config.rerank_fallback else 'failed'
                    reason = exc.reason
                    ranked = candidates if config.rerank_fallback else []
                finally:
                    rerank_observation(time.perf_counter() - started, config.rerank_model, len(candidates), status, reason)
                candidates = ranked
            with agent_span('knowledge.select_context') as context_span:
                matches = select_evidence(candidates, config)
                if context_span:
                    context_span.set_attribute('agent.retrieval.selected_ids', tuple(str(c['chunk_id']) for c in matches))
                    context_span.set_attribute('agent.retrieval.hits', len(matches))
            retrieval_hits(len(matches))
            if span:
                span.set_attribute('agent.retrieval.hits', len(matches))
            return matches
    except Exception as exc:
        logger.warning('Knowledge retrieval unavailable: %s', type(exc).__name__)
        return []
