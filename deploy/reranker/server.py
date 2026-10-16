"""Single-resident cross encoder; bounded work, no request contents in logs."""
from contextlib import asynccontextmanager
import math
import os
import threading
import time

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import torch
from transformers import AutoModelForSequenceClassification, AutoTokenizer

MODEL = os.environ.get('RERANK_MODEL', 'BAAI/bge-reranker-v2-m3')
REVISION = os.environ['RERANK_REVISION']
state = {'status': 'loading', 'model': MODEL, 'revision': REVISION, 'device': 'cpu'}
gate = threading.Lock()
tokenizer = model = None
batch_size = max(1, min(16, int(os.environ.get('RERANK_BATCH_SIZE', '4'))))


def load_model():
    global tokenizer, model
    try:
        torch.set_num_threads(max(1, int(os.environ.get('RERANK_THREADS', '4'))))
        tokenizer = AutoTokenizer.from_pretrained(MODEL, revision=REVISION, trust_remote_code=False)
        model = AutoModelForSequenceClassification.from_pretrained(
            MODEL, revision=REVISION, trust_remote_code=False, use_safetensors=True,
        ).eval()
        if torch.cuda.is_available():
            model = model.to('cuda').half()
            state['device'] = 'cuda'
        with torch.inference_mode():
            batch = tokenizer([['tea', 'Green tea is made from tea leaves.']], return_tensors='pt')
            model(**{k: v.to(model.device) for k, v in batch.items()})
        state['status'] = 'ready'
    except Exception as exc:
        state.update(status='error', error_type=type(exc).__name__)


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=load_model, daemon=True).start()
    yield


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': 'invalid_request'}, status_code=422)


@app.middleware('http')
async def bound_body(request: Request, call_next):
    if request.method == 'POST':
        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 1_000_000:
                return JSONResponse({'error': 'request_too_large'}, status_code=413)
        request._body = bytes(body)
    return await call_next(request)


class Document(BaseModel):
    index: int = Field(ge=0, le=99)
    text: str = Field(min_length=1, max_length=32000)


class RerankRequest(BaseModel):
    model: str
    query: str = Field(min_length=1, max_length=1000)
    documents: list[Document] = Field(min_length=1, max_length=100)
    deadline_ms: int = Field(default=5000, ge=500, le=30000)


@app.get('/health')
def health():
    return dict(state)


def score(payload):
    if state['status'] != 'ready':
        raise HTTPException(503, 'model_not_ready')
    if payload.model != MODEL:
        raise HTTPException(400, 'model_not_deployed')
    if len({d.index for d in payload.documents}) != len(payload.documents):
        raise HTTPException(400, 'duplicate_index')
    if not gate.acquire(blocking=False):
        raise HTTPException(429, 'inference_busy')
    started = time.monotonic()
    try:
        query = tokenizer.decode(tokenizer.encode(payload.query, add_special_tokens=False)[:96], skip_special_tokens=True)
        room = 512 - len(tokenizer.encode(query, add_special_tokens=False)) - 4
        windows = []
        for doc in payload.documents:
            offsets = tokenizer(doc.text, add_special_tokens=False, return_offsets_mapping=True)['offset_mapping']
            starts = list(range(0, max(1, len(offsets) - room + 1), room - 64))
            if starts and starts[-1] + room < len(offsets):
                starts.append(starts[-1] + room - 64)
            if len(starts) > 16 or len(windows) + len(starts) > 256:
                raise HTTPException(422, 'document_window_limit')
            for start in starts:
                part = offsets[start:start + room]
                excerpt = doc.text[part[0][0]:part[-1][1]] if part else doc.text
                windows.append((doc.index, excerpt))
        best = {}
        with torch.inference_mode():
            for pos in range(0, len(windows), batch_size):
                if (time.monotonic() - started) * 1000 >= payload.deadline_ms:
                    raise HTTPException(504, 'inference_deadline')
                group = windows[pos:pos + batch_size]
                batch = tokenizer([[query, text] for _, text in group], padding=True, truncation='only_second', max_length=512, return_tensors='pt')
                logits = model(**{k: v.to(model.device) for k, v in batch.items()}).logits.view(-1).float()
                scores = torch.sigmoid(logits).cpu().tolist()
                for (index, excerpt), value in zip(group, scores):
                    if not math.isfinite(value):
                        raise HTTPException(503, 'invalid_score')
                    if index not in best or value > best[index]['score']:
                        best[index] = {'index': index, 'score': value, 'excerpt': excerpt}
        if (time.monotonic() - started) * 1000 > payload.deadline_ms:
            raise HTTPException(504, 'inference_deadline')
        return {'model': MODEL, 'revision': REVISION, 'results': list(best.values()),
                'windows': len(windows), 'duration_ms': round((time.monotonic() - started) * 1000, 2)}
    finally:
        gate.release()


@app.post('/rerank')
def rerank(payload: RerankRequest):
    return score(payload)


@app.exception_handler(Exception)
async def safe_error(request, exc):
    return JSONResponse({'error': type(exc).__name__}, status_code=503)
