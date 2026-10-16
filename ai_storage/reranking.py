"""Local reranker protocol: server-selected models, immutable candidate identities."""
import math

import requests
from django.conf import settings


class RerankUnavailable(Exception):
    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def reranker_status():
    try:
        response = requests.get(settings.AI_RERANK_BASE_URL + '/health', timeout=(1, 2))
        response.raise_for_status()
        data = response.json()
        model = data.get('model')
        valid = model in settings.AI_RERANK_MODELS and data.get('revision') == settings.AI_RERANK_REVISION
        return {'status': data.get('status', 'unavailable') if valid else 'version_mismatch',
                'model': model if model in settings.AI_RERANK_MODELS else '',
                'revision': data.get('revision', '')[:100], 'device': data.get('device', 'unknown')[:20]}
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        return {'status': 'unavailable'}


def rerank_candidates(query, candidates, config):
    try:
        response = requests.post(
            settings.AI_RERANK_BASE_URL + '/rerank',
            json={'model': config.rerank_model, 'query': query,
                  'documents': [{'index': i, 'text': item['text']} for i, item in enumerate(candidates)],
                  'deadline_ms': config.rerank_timeout_ms},
            timeout=(min(1, config.rerank_timeout_ms / 1000), config.rerank_timeout_ms / 1000),
        )
        if response.status_code != 200:
            raise RerankUnavailable({429: 'busy', 503: 'not_ready', 504: 'timeout'}.get(response.status_code, 'service_error'))
        data = response.json()
        if data.get('model') != config.rerank_model or data.get('revision') != settings.AI_RERANK_REVISION:
            raise RerankUnavailable('version_mismatch')
        results = data.get('results')
        if not isinstance(results, list) or len(results) != len(candidates):
            raise RerankUnavailable('invalid_response')
        ranked, seen = [], set()
        for row in results:
            index, score, excerpt = row.get('index'), row.get('score'), row.get('excerpt')
            if (type(index) is not int or not 0 <= index < len(candidates) or index in seen
                    or type(score) not in (int, float) or not math.isfinite(score) or not 0 <= score <= 1
                    or not isinstance(excerpt, str) or not excerpt.strip() or excerpt not in candidates[index]['text']):
                raise RerankUnavailable('invalid_response')
            seen.add(index)
            ranked.append(dict(candidates[index], rerank_score=float(score), vector_rank=candidates[index].get('vector_rank', index + 1),
                               evidence_excerpt=excerpt))
        ranked.sort(key=lambda item: (-item['rerank_score'], item['vector_rank']))
        return [dict(item, rerank_rank=i + 1) for i, item in enumerate(ranked)]
    except RerankUnavailable:
        raise
    except requests.Timeout:
        raise RerankUnavailable('timeout') from None
    except (requests.RequestException, ValueError, TypeError, AttributeError):
        raise RerankUnavailable('service_error') from None
