"""Permission-filtered recall, local reranking and bounded evidence selection."""
import hashlib
import logging
import time
from dataclasses import replace

from django.conf import settings
from django.db import DatabaseError

from ai_storage.embeddings import embed_text
from ai_storage.knowledge import search_knowledge, search_knowledge_keywords, hybrid_search_ready
from .retrieval_cache import cached_embedding, evidence_key, read as cache_read, write as cache_write
from ai_storage.reranking import RerankUnavailable, rerank_candidates
from .telemetry import agent_span, retrieval_hits, rerank_observation
from .query_rewrite import (QueryPolicy, normalize_text, rule_queries, unique_queries, translate_queries,
                            insufficiency, focused_retry_queries, coverage_order, coverage_missing, SUBJECTS, FACETS, concepts)
from .pii import redact
from .grounding import COVERAGE_PENDING, COVERAGE_UNCONFIRMED
from .retry_decision import build_focused_query, decide_retry, needs_semantic_review

RETRY_TIME_RESERVE = 2.0
ANSWER_TIME_RESERVE = 5.0

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
        return retrieve_knowledge(query, owner_id, scoped, retriever=retriever, scoped=True)
    return retrieve_knowledge(query, owner_id, scoped, scoped=True)


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
            truncated = item.get('context_truncated', False)
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
        self.tool_deadline = self.request_deadline = None
        self.ordinary_retry_used = False

    def search(self, query):
        return retrieve_knowledge(query, self.owner_id, self.config, retriever=self)

    def scoped_search(self, query, category, scope):
        return retrieve_scoped_knowledge(query, self.owner_id, self.config, category, scope, retriever=self)

    def notes(self):
        if not self.audit:
            return []
        audit = self.audit[-1]
        target = audit.get('semantic_target')
        notes = ['{}:{}:{}'.format(COVERAGE_PENDING, *target)] if target else []
        missing = [SUBJECTS[k][0] for k in audit.get('missing_subjects', [])
                   if not target or k != target[0]]
        if missing:
            notes.append('本次检索未找到同时覆盖{}与所问主题的直接证据；回答应明确资料缺口，不据此推断。'.format('、'.join(missing)))
        elif not target and audit.get('remaining_issues'):
            notes.append('本次检索存在资料数量或关联性不足的信号；请仅回答证据直接支持的内容，并说明限制。')
        if not target and audit.get('selected_ids') and audit.get('semantic_status') in (
                'pending', 'rejected', 'unavailable'):
            notes.append(COVERAGE_UNCONFIRMED)
        if target and 'year_gap' in audit.get('remaining_issues', []):
            notes.append('本次检索缺少所问年份的直接资料。')
        return notes

    def remaining_seconds(self):
        now = time.monotonic()
        deadlines = [deadline for deadline in (self.request_deadline, self.tool_deadline) if deadline is not None]
        if self.started is not None:
            deadlines.append(self.started + self.policy.budget_seconds)
        return min((deadline - now for deadline in deadlines), default=self.policy.budget_seconds)

    def has_budget(self):
        return self.remaining_seconds() > 0

    def rewrite_seconds(self):
        available = self.remaining_seconds() - RETRY_TIME_RESERVE
        if self.request_deadline is not None:
            available = min(available, self.request_deadline - time.monotonic()
                            - ANSWER_TIME_RESERVE - RETRY_TIME_RESERVE)
        return available

    def _rewrite_model(self, context_chars):
        if self.model_factory:
            return self.model_factory()
        from .model_client import configured_model
        timeout = self.policy.model_timeout
        if context_chars:
            timeout = min(timeout, self.rewrite_seconds())
        return configured_model(self.config, timeout=timeout, max_retries=0, max_tokens=1400,
                                grounding_context_chars=context_chars)

    def _take_rewrite_slot(self, audit, context_chars):
        available = self.rewrite_seconds() - 1 if context_chars else self.remaining_seconds()
        if self.model_calls >= self.policy.max_model_calls or available <= 0:
            audit['rewrite_status'].append('request_budget')
            return False
        self.model_calls += 1
        return True

    def generate(self, query, audit, issues=(), attempted=(), *, context_chars=0):
        if not self._take_rewrite_slot(audit, context_chars):
            return []
        try:
            if self.model is None:
                self.model = self._rewrite_model(context_chars)
            with agent_span('knowledge.query_rewrite') as span:
                queries, rejected = translate_queries(self.model, query, issues, attempted, self.policy.languages)
                if span:
                    span.set_attribute('agent.rewrite.variants', len(queries))
                    span.set_attribute('agent.rewrite.rejected', rejected)
                audit['rewrite_status'].append('translated' if queries else 'no_valid_variants')
                audit['rejected_variants'] += rejected
                return queries
        except Exception as exc:
            self._rewrite_failed(audit, exc)
            return []

    def semantic_query(self, query, evidence, audit, context_chars):
        if not self._take_rewrite_slot(audit, context_chars):
            return None
        try:
            with agent_span('knowledge.query_rewrite') as span:
                decision = decide_retry(self._rewrite_model(context_chars), query, evidence, context_chars=context_chars)
                if decision.action == 'answer':
                    audit['semantic_status'] = 'answer'
                    return None
                focused = build_focused_query(query, decision)
                if focused is None:
                    audit['semantic_status'] = 'rejected'
                    return None
                audit['semantic_status'] = 'search_again'
                audit['semantic_target'] = [decision.target, decision.facet]
                if span:
                    span.set_attribute('agent.rewrite.variants', 1)
                return focused
        except Exception as exc:
            audit['semantic_status'] = 'unavailable'
            self._rewrite_failed(audit, exc)
            return None

    @staticmethod
    def _rewrite_failed(audit, exc):
        audit['rewrite_status'].append('fallback')
        audit['rewrite_error_types'].append(type(exc).__name__)
        logger.warning('support.query_rewrite.unavailable', extra={'error_type': type(exc).__name__})

    def initial_queries(self, query, audit, max_queries):
        audit['rewrite_status'].append('deferred')
        return unique_queries(rule_queries(query), max_queries)


def chunk_key(item):
    return item['document_id'], item['chunk_id']


def fuse_rankings(rankings, limit):
    """RRF uses ranks, never adds incomparable embedding/reranker scores."""
    rows = {}
    for query_index, ranking in enumerate(rankings):
        seen = set()
        for rank, item in enumerate(ranking, 1):
            key = chunk_key(item)
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
        if (index or round_number) and not retriever.has_budget():
            item['status'] = 'request_budget'
            continue
        try:
            attrs = {'agent.retrieval.round':round_number, 'agent.retrieval.query_index':index}
            with agent_span('knowledge.vector_route', attrs):
                if query in retriever.embeddings:
                    with agent_span('knowledge.cache', {'agent.cache.kind':'embedding', 'agent.cache.status':'request_hit'}):
                        embedding = retriever.embeddings[query]
                else:
                    remaining = max(0.1, retriever.remaining_seconds())
                    retriever.embeddings[query] = cached_embedding(query, embed_text, timeout=(min(2, remaining), min(8, remaining)))
                    embedding = retriever.embeddings[query]
                with agent_span('knowledge.vector_search', attrs) as span:
                    ranking = search_knowledge(embedding, settings.AI_EMBEDDING_SPACE_KEY, owner_id, limit=limit)
                    if span:
                        span.set_attribute('agent.retrieval.hits', len(ranking))
            item['hits'] = len(ranking)
            rankings.append(ranking)
        except Exception as exc:
            item['status'], item['error_type'] = 'error', type(exc).__name__
            logger.warning('support.query_route.unavailable', extra={'error_type': type(exc).__name__})
    return rankings


def _hybrid_recall(queries, owner_id, budget, retriever, audit, round_number):
    """Independent keyword and vector routes with the same trusted ACL."""
    if round_number and not retriever.has_budget():
        return []
    if budget < 2 or not getattr(settings, 'SUPPORT_RAG_HYBRID_ENABLED', True):
        return _recall_queries(queries, owner_id, budget, retriever, audit, round_number)
    try:
        with agent_span('knowledge.hybrid_ready'):
            ready = hybrid_search_ready()
    except DatabaseError as exc:
        if not round_number:
            raise
        audit['queries'].append({'round': round_number, 'channel': 'hybrid_ready',
                                 'hits': 0, 'status': 'error', 'error_type': type(exc).__name__})
        return []
    if not ready:
        audit['hybrid_status'] = 'schema_pending'
        return _recall_queries(queries, owner_id, budget, retriever, audit, round_number)
    audit['hybrid_status'] = 'enabled'
    keyword_budget = max(1, budget // 2)
    item = {'round': round_number, 'channel': 'keyword', 'limit': keyword_budget, 'hits': 0, 'status': 'success'}
    audit['queries'].append(item)
    rankings = []
    try:
        with agent_span('knowledge.keyword_search', {'agent.retrieval.round':round_number}) as span:
            rows = search_knowledge_keywords(' '.join(queries), owner_id, limit=keyword_budget)
            if span:
                span.set_attribute('agent.retrieval.hits', len(rows))
        item['hits'] = len(rows)
        rankings.append(rows)
    except Exception as exc:
        item.update(status='error', error_type=type(exc).__name__)
        logger.warning('support.keyword_route.unavailable', extra={'error_type': type(exc).__name__})
    rankings.extend(_recall_queries(queries, owner_id, max(1, budget-keyword_budget), retriever, audit, round_number))
    return rankings


def _rank_candidates(query, candidates, config, retriever, audit, *, priority=None):
    cap = max(1, min(config.retrieval_candidates, int(getattr(settings, 'SUPPORT_RAG_RERANK_CANDIDATES', 20))))
    candidates = coverage_order(query, candidates)
    if priority is not None:
        # Keep one gap candidate in the scorer's input even if the first
        # round filled the global RRF window. The score still uses the original.
        candidates = [priority] + [item for item in candidates if chunk_key(item) != chunk_key(priority)]
    candidates = candidates[:cap]
    attrs = {'agent.rerank.model':config.rerank_model, 'agent.rerank.revision':settings.AI_RERANK_REVISION,
             'agent.rerank.candidates':len(candidates)}
    has_budget = retriever.has_budget()
    skipped = not config.rerank_enabled or not candidates or not has_budget
    with agent_span('knowledge.rerank.skipped' if skipped else 'knowledge.rerank', attrs) as span:
        if not config.rerank_enabled or not candidates:
            if span:
                span.set_attribute('agent.rerank.status', 'disabled' if not config.rerank_enabled else 'empty')
            return candidates
        if not has_budget:
            audit['rerank_status'].append('request_budget')
            if span:
                span.set_attribute('agent.rerank.status', 'request_budget')
            return candidates if config.rerank_fallback else []
        started, status, reason = time.perf_counter(), 'success', ''
        try:
            remaining_ms = max(1, int(retriever.remaining_seconds() * 1000))
            bounded = replace(config, rerank_timeout_ms=min(config.rerank_timeout_ms, remaining_ms))
            if span:
                span.set_attribute('agent.rerank.input_ids', tuple(str(c['chunk_id']) for c in candidates))
            ranked = rerank_candidates(query, candidates, bounded)
            if span:
                span.set_attribute('agent.rerank.output_ids', tuple(str(c['chunk_id']) for c in ranked))
                span.set_attribute('agent.rerank.scores', tuple(c['rerank_score'] for c in ranked))
            return ranked
        except RerankUnavailable as exc:
            status, reason = ('fallback' if config.rerank_fallback else 'failed'), exc.reason
            if span:
                from opentelemetry.trace import Status, StatusCode
                span.set_status(Status(StatusCode.ERROR))
            return candidates if config.rerank_fallback else []
        finally:
            if span:
                span.set_attribute('agent.rerank.status', status)
                if reason:
                    span.set_attribute('agent.rerank.reason', reason)
            audit['rerank_status'].append(status)
            rerank_observation(time.perf_counter()-started, config.rerank_model, len(candidates), status, reason)


def retry_plan(query, evidence, reasons, queries, retriever, audit, config, semantic):
    compare = semantic and evidence and needs_semantic_review(query)
    if compare and retriever.policy.retry_enabled:
        audit['semantic_status'] = 'pending'
    if (not retriever.policy.retry_enabled or not retriever.has_budget()
            or (semantic and retriever.ordinary_retry_used)):
        return []
    attempted = {normalize_text(q).casefold() for q in queries}

    def unused(values):
        return [q for q in values if normalize_text(q).casefold() not in attempted]

    direct = unused(focused_retry_queries(query, evidence)) if reasons else []
    if semantic and direct:
        audit['semantic_status'] = 'rule'
        values = direct
    elif reasons:
        if semantic:
            audit['semantic_status'] = 'rule'
        generated = retriever.generate(query, audit, reasons, queries,
                                       context_chars=config.retrieval_context_chars if semantic else 0)
        values = [*direct, *generated, *rule_queries(query)]
    elif compare:
        focused = retriever.semantic_query(query, evidence, audit, config.retrieval_context_chars)
        values = [focused] if focused else []
    else:
        return []
    limit = 1 if audit.get('semantic_target') else min(2, retriever.policy.max_queries)
    return unique_queries(unused(values), limit)


def merge_focused_evidence(query, first, ranked, novel_keys, target, config):
    # Make room only where it cannot remove the other side of the question.
    # Co-occurrence is not enough to decide that two passages are substitutes.
    if config.retrieval_top_k < 2:
        return first
    kept = first
    if len(first) >= config.retrieval_top_k:
        subjects = set(concepts(query, SUBJECTS))
        protected = subjects if len(concepts(query, FACETS)) > 1 else subjects - {target}
        removable = next((i for i in range(len(first) - 1, 0, -1)
                          if not protected.intersection(concepts(first[i]['text'], SUBJECTS))), None)
        if removable is None:
            return first
        kept = first[:removable] + first[removable + 1:]
    for item in ranked:
        if chunk_key(item) not in novel_keys or target not in concepts(item['text'], SUBJECTS):
            continue
        if config.rerank_min_score is not None and item.get('rerank_score', 1) < config.rerank_min_score:
            continue
        if sum(row['document_id'] == item['document_id'] for row in kept) >= config.retrieval_per_document:
            continue
        remaining = config.retrieval_context_chars - sum(len(row['text']) for row in kept)
        if remaining <= 0:
            continue
        new = select_evidence([item], replace(config, retrieval_context_chars=remaining))
        if new and set(coverage_missing(query, kept + new)) <= set(coverage_missing(query, first)):
            return kept + new
    return first


def retrieve_knowledge(query, owner_id, config, retriever=None, *, scoped=False):
    with agent_span('knowledge.retrieve') as span:
        evidence = _retrieve_knowledge(query, owner_id, config, retriever, scoped=scoped)
        retrieval_hits(len(evidence))
        if span:
            span.set_attribute('agent.retrieval.hits', len(evidence))
        return evidence


def _retrieve_knowledge(query, owner_id, config, retriever=None, *, scoped=False):
    retriever = retriever or KnowledgeRetriever(owner_id, config)
    if owner_id != retriever.owner_id:
        raise ValueError('Retrieval scope mismatch')
    if not retriever.policy.enabled:
        return _retrieve_single(query, owner_id, config)
    query = normalize_text(redact(query))
    if not query or len(query) > 1600:
        return []
    semantic = retriever.policy.semantic_retry_enabled and not scoped
    mode = 'scoped' if scoped else 'ordinary'
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
    with agent_span('knowledge.cache', {'agent.cache.kind':'evidence'}) as span:
        key = evidence_key(query, owner_id, config, retriever.policy, mode=mode)
        cached = cache_read(key)
        if span:
            span.set_attribute('agent.cache.status', 'hit' if cached is not None else 'miss' if key else 'disabled')
    if cached is not None:
        evidence, saved_audit = cached
        audit.update(saved_audit, cache_status='hit')
        return evidence
    audit['cache_status'] = 'miss' if key else 'disabled'
    with agent_span('knowledge.recall') as span:
        max_queries = min(retriever.policy.max_queries, config.retrieval_candidates)
        queries = retriever.initial_queries(query, audit, max_queries)
        rankings = _hybrid_recall(queries, owner_id, config.retrieval_candidates, retriever, audit, 0)
        with agent_span('knowledge.rrf') as rrf_span:
            fused = fuse_rankings(rankings, config.retrieval_candidates)
            if rrf_span:
                rrf_span.set_attribute('agent.retrieval.candidates', len(fused))
        # Rank against the original redacted, normalized knowledge question.
        # Translations and expansions broaden recall only, including on retry.
        ranked = _rank_candidates(query, fused, config, retriever, audit)
        with agent_span('knowledge.select_context') as select_span:
            evidence = select_evidence(coverage_order(query, ranked), config)
            if select_span:
                select_span.set_attribute('agent.retrieval.hits', len(evidence))
        reasons = insufficiency(query, evidence, config, retriever.policy)
        audit['retry_reasons'] = reasons
        retry_queries = retry_plan(query, evidence, reasons, queries, retriever, audit, config, semantic)
        if retry_queries and retriever.has_budget():
            with agent_span('knowledge.retry', {'agent.retrieval.retry_reasons':tuple(reasons)}):
                if semantic:
                    retriever.ordinary_retry_used = True
                audit['retry'] = True
                retry_cap = max(1, config.retrieval_candidates // 2)
                extra = _hybrid_recall(retry_queries, owner_id, retry_cap, retriever, audit, 1)
                if extra:
                    combined = fuse_rankings([*rankings, *extra], config.retrieval_candidates)
                    old_keys = {chunk_key(item) for rows in rankings for item in rows}
                    target = audit.get('semantic_target')
                    if target:
                        novelty = [item for item in deduplicate([
                            *(item for rows in rankings for item in rows),
                            *fuse_rankings(extra, retry_cap),
                        ]) if chunk_key(item) not in old_keys and target[0] in concepts(item['text'], SUBJECTS)]
                        if novelty:
                            rescored = _rank_candidates(query, combined, config, retriever, audit, priority=novelty[0])
                            supplemental = merge_focused_evidence(query, evidence, rescored,
                                                                  {chunk_key(item) for item in novelty}, target[0], config)
                            audit['retry_adopted'] = supplemental is not evidence
                            evidence = supplemental
                    else:
                        rescored = (_rank_candidates(query, combined, config, retriever, audit)
                                    if {chunk_key(item) for item in combined} - old_keys else ranked)
                        if rescored:
                            supplemental = select_evidence(coverage_order(query, rescored), config)

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
    decision_complete = audit.get('semantic_status') in (None, 'rule', 'answer')
    if evidence and decision_complete and not audit['remaining_issues'] and not failed and not audit['rewrite_error_types'] and all(
            s == 'success' for s in audit['rerank_status']):
        # A concurrent mutation must not install evidence under the new epoch.
        if key is not None and key == evidence_key(query, owner_id, config, retriever.policy, mode=mode):
            with agent_span('knowledge.cache_write'):
                cache_write(key, (evidence, audit))
    return evidence


def _retrieve_single(query, owner_id, config):
    try:
        with agent_span('knowledge.recall') as span:
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
            if span:
                span.set_attribute('agent.retrieval.hits', len(matches))
            return matches
    except Exception as exc:
        logger.warning('support.retrieval.unavailable', extra={'error_type': type(exc).__name__})
        raise RetrievalUnavailable('Knowledge retrieval is unavailable') from None
