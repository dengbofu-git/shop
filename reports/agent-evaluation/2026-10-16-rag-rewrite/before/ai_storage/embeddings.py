"""Local Ollama embedding adapter shared by ingestion and semantic queries."""

import requests
from django.conf import settings


def embed_texts(texts):
    if not texts or any(not isinstance(text, str) or not text.strip() for text in texts):
        raise ValueError('embedding inputs must be non-empty strings')
    response = requests.post(
        settings.AI_OLLAMA_BASE_URL + '/api/embed',
        json={'model': settings.AI_OLLAMA_MODEL, 'input': texts, 'truncate': False},
        timeout=(10, 300),
    )
    response.raise_for_status()
    data = response.json()
    vectors = data.get('embeddings')
    if not isinstance(vectors, list) or len(vectors) != len(texts):
        raise ValueError('Ollama returned an unexpected embedding batch')
    dimensions = len(vectors[0]) if vectors else 0
    if dimensions == 0 or any(not isinstance(vector, list) or len(vector) != dimensions for vector in vectors):
        raise ValueError('Ollama returned vectors with inconsistent dimensions')
    return vectors


def embed_text(text):
    return embed_texts([text])[0]
