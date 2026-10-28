"""Permission-filtered recall, local reranking and bounded evidence selection."""
import hashlib
import logging
import time
from dataclasses import replace

from django.conf import settings

from ai_storage.embeddings import embed_text
from ai_storage.knowledge import search_knowledge, search_knowledge_keywords, hybrid_search_ready
from .retrieval_cache import cached_embedding, evidence_key, read as cache_read, write as cache_write
from ai_storage.reranking import RerankUnavailable, rerank_candidates
from .telemetry import agent_span, retrieval_hits, rerank_observation
from .query_rewrite import (QueryPolicy, normalize_text, rule_queries, unique_queries, translate_queries,
                            insufficiency, focused_retry_queries, coverage_order, coverage_missing, SUBJECTS, FACETS, concepts)
from .pii import redact

logger = logging.getLogger(__name__)


class RetrievalUnavailable(RuntimeError):
    """Technical failure must not masquerade as a knowledge gap."""


def retrieve_scoped_knowledge(query, owner_id, config, category, scope, retriever=None):
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
    if retriever is not None:
        return retrieve_knowledge(query, owner_id, scoped, retriever=retriever)
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


class KnowledgeRetriever:
    """One instance per chat request: budgets and caches never cross user scopes."""

    def __init__(self, owner_id, config, model_factory=None):
        if owner_id is not None and (type(owner_id) is not int or owner_id <= 0):
            raise ValueError('Invalid trusted owner')
        self.owner_id, self.config = owner_id, config
        self.policy = QueryPolicy.current()
        self.model_factory, self.model = model_factory, None
        self.model_calls, self.started = 0, None
        self.embeddings, self.audit = {}, []

    def search(self, query):
        return retrieve_knowledge(query, self.owner_id, self.config, retriever=self)

    def scoped_search(self, query, category, scope):
        return retrieve_scoped_knowledge(query, self.owner_id, self.config, category, scope, retriever=self)

    def notes(self):
        if not self.audit or not self.audit[-1].get('remaining_issues'):
            return []
        audit = self.audit[-1]
        missing = [SUBJECTS[k][0] for k in audit.get('missing_subjects', [])]
        if missing:
            return ['本次检索未找到同时覆盖{}与所问主题的直接证据；回答应明确资料缺口，不据此推断。'.format('、'.join(missing))]
        return ['本次检索存在资料数量或关联性不足的信号；请仅回答证据直接支持的内容，并说明限制。']

    def has_budget(self):
        return self.started is None or time.monotonic() - self.started < self.policy.budget_seconds

    def generate(self, query, audit, issues=(), attempted=()):
        if self.model_calls >= self.policy.max_model_calls or not self.has_budget():
            audit['rewrite_status'].append('request_budget')
            return []
        self.model_calls += 1
        try:
            if self.model is None:
                from .model_client import configured_model
                self.model = self.model_factory() if self.model_factory else configured_model(
                    self.config, timeout=self.policy.model_timeout, max_retries=0, max_tokens=1400)
            with agent_span('knowledge.query_rewrite') as span:
                queries, rejected = translate_queries(self.model, query, issues, attempted, self.policy.languages)
                if span:
                    span.set_attribute('agent.rewrite.variants', len(queries))
                    span.set_attribute('agent.rewrite.rejected', rejected)
                audit['rewrite_status'].append('translated' if queries else 'no_valid_variants')
                audit['rejected_variants'] += rejected
                return queries
        except Exception as exc:
            # The original query and lexical expansion survive provider failure.
            audit['rewrite_status'].append('fallback')
            audit['rewrite_error_types'].append(type(exc).__name__)
            logger.warning('support.query_rewrite.unavailable', extra={'error_type': type(exc).__name__})
            return []

    def initial_queries(self, query, audit, max_queries):
        audit['rewrite_status'].append('deferred')
        return unique_queries(rule_queries(query), max_queries)


def fuse_rankings(rankings, limit):
    """RRF uses ranks, never adds incomparable embedding/reranker scores."""
    rows = {}
    for query_index, ranking in enumerate(rankings):
        seen = set()
        for rank, item in enumerate(ranking, 1):
            key = (item['document_id'], item['chunk_id'])
            if key in seen:
                continue
            seen.add(key)
            if key not in rows:
                rows[key] = dict(item, rrf_score=0.0, query_ranks=[], first_seen=len(rows))
            rows[key]['rrf_score'] += 1 / (60 + rank)
            rows[key]['query_ranks'].append({'query_index':query_index, 'rank':rank})
    ranked = sorted(rows.values(), key=lambda r:(-r['rrf_score'], r['first_seen']))
    return [dict(item, vector_rank=i + 1) for i, item in enumerate(deduplicate(ranked)[:limit])]


def _recall_queries(queries, owner_id, budget, retriever, audit, round_number):
    """The sum of returned per-route candidates cannot exceed this round's budget."""
    queries = queries[:budget]
    if not queries:
        return []
    # Keep half the slots for the original query in the first round.
    first = max(1, budget // 2) if len(queries) > 1 else budget
    first = min(first, budget - len(queries) + 1)
    left = budget - first
    limits = [first] + ([left // (len(queries)-1) + (i < left % (len(queries)-1))
                         for i in range(len(queries)-1)] if len(queries) > 1 else [])
    rankings = []
    for index, (query, limit) in enumerate(zip(queries, limits)):
        item = {'round':round_number, 'channel':'vector', 'query':query, 'limit':limit, 'hits':0, 'status':'success'}
        audit['queries'].append(item)
        if index and not retriever.has_budget():
            item['status'] = 'request_budget'
            continue
        try:
            with agent_span('knowledge.embedding'):
                if query not in retriever.embeddings:
                    remaining = max(1, retriever.policy.budget_seconds - (time.monotonic()-retriever.started))
                    retriever.embeddings[query] = cached_embedding(query, embed_text, timeout=(2, min(8, remaining)))
                embedding = retriever.embeddings[query]
            with agent_span('knowledge.vector_search'):
                ranking = search_knowledge(embedding, settings.AI_EMBEDDING_SPACE_KEY, owner_id, limit=limit)
            item['hits'] = len(ranking)
            rankings.append(ranking)
        except Exception as exc:
            item['status'], item['error_type'] = 'error', type(exc).__name__
            logger.warning('support.query_route.unavailable', extra={'error_type': type(exc).__name__})
    return rankings


def _hybrid_recall(queries, owner_id, budget, retriever, audit, round_number):
    """Independent keyword and vector routes with the same trusted ACL."""
    if budget < 2 or not getattr(settings, 'SUPPORT_RAG_HYBRID_ENABLED', True):
        return _recall_queries(queries, owner_id, budget, retriever, audit, round_number)
    if not hybrid_search_ready():
        audit['hybrid_status'] = 'schema_pending'
        return _recall_queries(queries, owner_id, budget, retriever, audit, round_number)
    audit['hybrid_status'] = 'enabled'
    keyword_budget = max(1, budget // 2)
    item = {'round': round_number, 'channel': 'keyword', 'limit': keyword_budget, 'hits': 0, 'status': 'success'}
    audit['queries'].append(item)
    rankings = []
    try:
        rows = search_knowledge_keywords(' '.join(queries), owner_id, limit=keyword_budget)
        item['hits'] = len(rows)
        rankings.append(rows)
    except Exception as exc:
        item.update(status='error', error_type=type(exc).__name__)
        logger.warning('support.keyword_route.unavailable', extra={'error_type': type(exc).__name__})
    rankings.extend(_recall_queries(queries, owner_id, max(1, budget-keyword_budget), retriever, audit, round_number))
    return rankings


def _rank_candidates(query, candidates, config, retriever, audit):
    cap = max(1, min(100, int(getattr(settings, 'SUPPORT_RAG_RERANK_CANDIDATES', 20))))
    # Preserve explicit comparison subjects before limiting expensive scoring.
    candidates = coverage_order(query, candidates)[:cap]
    if not config.rerank_enabled or not candidates:
        return candidates
    if not retriever.has_budget():
        audit['rerank_status'].append('request_budget')
        # Respect fail-closed deployments even when dispatch budget expires.
        return candidates if config.rerank_fallback else []
    started, status, reason = time.perf_counter(), 'success', ''
    try:
        remaining_ms = max(500, int((retriever.policy.budget_seconds - (time.monotonic()-retriever.started)) * 1000))
        bounded = replace(config, rerank_timeout_ms=min(config.rerank_timeout_ms, remaining_ms))
        with agent_span('knowledge.rerank', {'agent.rerank.model':config.rerank_model,
                        'agent.rerank.revision':settings.AI_RERANK_REVISION,
                        'agent.rerank.candidates':len(candidates),
                        'agent.rerank.input_ids':tuple(str(c['chunk_id']) for c in candidates)}) as span:
            ranked = rerank_candidates(query, candidates, bounded)
            if span:
                span.set_attribute('agent.rerank.output_ids', tuple(str(c['chunk_id']) for c in ranked))
                span.set_attribute('agent.rerank.scores', tuple(c['rerank_score'] for c in ranked))
        return ranked
    except RerankUnavailable as exc:
        status, reason = ('fallback' if config.rerank_fallback else 'failed'), exc.reason
        return candidates if config.rerank_fallback else []
    finally:
        audit['rerank_status'].append(status)
        rerank_observation(time.perf_counter()-started, config.rerank_model, len(candidates), status, reason)


def retrieve_knowledge(query, owner_id, config, retriever=None):
    retriever = retriever or KnowledgeRetriever(owner_id, config)
    if owner_id != retriever.owner_id:
        raise ValueError('Retrieval scope mismatch')
    if not retriever.policy.enabled:
        return _retrieve_single(query, owner_id, config)
    query = normalize_text(redact(query))
    if not query or len(query) > 1600:
        return []
    multiple = len(concepts(query, SUBJECTS)) > 1
    char_cap = int(getattr(settings, 'SUPPORT_RAG_MULTI_CONTEXT_CHARS' if multiple else 'SUPPORT_RAG_SINGLE_CONTEXT_CHARS',
                           8000 if multiple else 3000))
    config = replace(config, retrieval_context_chars=min(config.retrieval_context_chars, max(200, char_cap)))
    if retriever.started is None:
        retriever.started = time.monotonic()
    audit = {'original_query':query, 'rewrite_status':[], 'rewrite_error_types':[], 'rejected_variants':0,
             'queries':[], 'rerank_status':[], 'retry':False, 'retry_adopted':False,
             'retry_reasons':[], 'selected_ids':[]}
    retriever.audit.append(audit)
    key = evidence_key(query, owner_id, config, retriever.policy)
    cached = cache_read(key)
    if cached is not None:
        evidence, saved_audit = cached
        audit.update(saved_audit, cache_status='hit')
        return evidence
    audit['cache_status'] = 'miss' if key else 'disabled'
    with agent_span('knowledge.retrieve') as span:
        max_queries = min(retriever.policy.max_queries, config.retrieval_candidates)
        queries = retriever.initial_queries(query, audit, max_queries)
        rankings = _hybrid_recall(queries, owner_id, config.retrieval_candidates, retriever, audit, 0)
        with agent_span('knowledge.rrf'):
            fused = fuse_rankings(rankings, config.retrieval_candidates)
        # Rank against the original redacted, normalized knowledge question.
        # Translations and expansions broaden recall only, including on retry.
        ranked = _rank_candidates(query, fused, config, retriever, audit)
        evidence = select_evidence(coverage_order(query, ranked), config)
        reasons = insufficiency(query, evidence, config, retriever.policy)
        audit['retry_reasons'] = reasons
        if reasons and retriever.policy.retry_enabled and retriever.has_budget():
            with agent_span('knowledge.retry', {'agent.retrieval.retry_reasons':tuple(reasons)}):
                generated = retriever.generate(query, audit, reasons, queries)
                attempted = {x.casefold() for x in queries}
                retry_queries = unique_queries([q for q in [*focused_retry_queries(query, evidence),
                    *generated, *rule_queries(query)] if normalize_text(q).casefold() not in attempted],
                    limit=min(2, retriever.policy.max_queries))
                if retry_queries:
                    audit['retry'] = True
                    extra = _hybrid_recall(retry_queries, owner_id, max(1, config.retrieval_candidates//2), retriever, audit, 1)
                    if extra:
                        rankings.extend(extra)
                        fused = fuse_rankings(rankings, config.retrieval_candidates)
                        old_ids = {(x['document_id'], x['chunk_id']) for rows in rankings[:-len(extra)] for x in rows}
                        new_ids = {(x['document_id'], x['chunk_id']) for x in fused}
                        retry_ranked = _rank_candidates(query, fused, config, retriever, audit) if new_ids - old_ids else ranked
                        # A failed supplemental service cannot erase first-round evidence.
                        if retry_ranked:
                            supplemental = select_evidence(coverage_order(query, retry_ranked), config)
                            def quality(values):
                                scores = [v['rerank_score'] for v in values if 'rerank_score' in v]
                                return (len(coverage_missing(query, values)),
                                        len(insufficiency(query, values, config, retriever.policy)),
                                        -max(scores, default=0))
                            if quality(supplemental) <= quality(evidence):
                                evidence = supplemental
                                audit['retry_adopted'] = True
        audit['remaining_issues'] = insufficiency(query, evidence, config, retriever.policy)
        audit['missing_subjects'] = coverage_missing(query, evidence)
        subjects = concepts(query, SUBJECTS)
        audit['coverage'] = {'covered_subjects': [s for s in subjects if s not in audit['missing_subjects']],
            'missing_subjects': audit['missing_subjects'],
            'missing_facets': [f for f in concepts(query, FACETS)
                               if not any(f in concepts(e['text'], FACETS) for e in evidence)]}
        audit['selected_ids'] = [str(e['chunk_id']) for e in evidence]
        with agent_span('knowledge.select_context', {'agent.retrieval.hits':len(evidence),
                        'agent.retrieval.selected_ids':tuple(audit['selected_ids'])}):
            retrieval_hits(len(evidence))
        if span:
            span.set_attribute('agent.retrieval.hits', len(evidence))
            span.set_attribute('agent.retrieval.queries', len(audit['queries']))
            span.set_attribute('agent.retrieval.retries', int(audit['retry']))
            span.set_attribute('agent.retrieval.retry_reasons', tuple(reasons))
            span.set_attribute('agent.retrieval.remaining_issues', tuple(audit['remaining_issues']))
            span.set_attribute('agent.retrieval.retry_adopted', audit['retry_adopted'])
            span.set_attribute('agent.rewrite.status', tuple(audit['rewrite_status']))
    # Never cache service failures, empty evidence or an unfinished coverage search.
    failed = any(q['status'] != 'success' for q in audit['queries'])
    if not evidence and failed:
        raise RetrievalUnavailable('Knowledge recall incomplete because a route is unavailable')
    if not evidence and any(s in ('failed', 'request_budget') for s in audit['rerank_status']):
        raise RetrievalUnavailable('Required knowledge ranking unavailable')
    if evidence and not audit['remaining_issues'] and not failed and not audit['rewrite_error_types'] and all(
            s == 'success' for s in audit['rerank_status']):
        # A concurrent mutation must not install evidence under the new epoch.
        if key is not None and key == evidence_key(query, owner_id, config, retriever.policy):
            cache_write(key, (evidence, audit))
    return evidence


def _retrieve_single(query, owner_id, config):
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
        logger.warning('support.retrieval.unavailable', extra={'error_type': type(exc).__name__})
        return []
