"""Single-process GPU document service; deliberately imports no application/ORM code."""
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import threading
import time
import traceback
import uuid


CONTRACT = 'paddle-document-v1'
MODEL = 'PaddleOCR-VL-1.6-0.9B'
MAX_BODY = 28000000


def sha256(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def plain(value):
    if isinstance(value, dict):
        return {key: plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [plain(item) for item in value]
    return value


class Runtime:
    def __init__(self, pipeline=None, identity=None):
        self.pipeline, self.identity = pipeline, identity
        self.ready = pipeline is not None
        self.gate = threading.Lock()
        self.generations = []
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='gpu-owner')

    def execute(self, data, maximum):
        # Load and execute in one persistent owner thread; framework contexts and
        # static-layout predictors must not migrate across arbitrary HTTP threads.
        return self.executor.submit(self.infer, data, maximum).result()

    def load(self):
        from importlib.metadata import version
        import paddle
        from paddleocr import PaddleOCRVL
        from paddlex import create_predictor
        from paddlex.inference import load_pipeline_config

        if version('paddleocr') != '3.6.0' or version('paddlex') != '3.6.1':
            raise RuntimeError('UNSUPPORTED_PINNED_RUNTIME')
        config = plain(load_pipeline_config('PaddleOCR-VL-1.6'))
        config.update(batch_size=1, use_queues=False, use_doc_preprocessor=False, use_layout_detection=False)
        config['SubModules']['LayoutDetection']['batch_size'] = 1
        config['SubModules']['VLRecognition']['batch_size'] = 1
        cache = Path.home() / '.paddlex/official_models'
        weights = {
            'layout': sha256(cache / 'PP-DocLayoutV3/inference.pdiparams'),
            'recognition': sha256(cache / 'PaddleOCR-VL-1.6/model.safetensors'),
        }
        expected = {'layout': '70bd316b0582769ec968829fd1feb1a6a58b7c941b938327e551b6b12b45c137',
                    'recognition': '85a479d506a11e724e7285d395c551be69f41dbc16b6342d3cacfb189aed71db'}
        if weights != expected:
            raise RuntimeError('MODEL_WEIGHTS_CHANGED')
        material = {'weights': weights, 'pipeline': config,
                    'packages': {name: version(name) for name in ('paddleocr', 'paddlex', 'paddlepaddle-gpu')},
                    'service_sha256': sha256(__file__), 'layout_device': 'cpu', 'contract': CONTRACT}
        revision = hashlib.sha256(json.dumps(material, sort_keys=True).encode()).hexdigest()
        self.identity = {'model': MODEL, 'revision': revision, 'contract_version': CONTRACT,
                         'pipeline_version': 'v1.6', 'weights': weights}
        self.pipeline = PaddleOCRVL(pipeline_version='v1.6', paddlex_config=config, device='gpu:0',
                                   use_doc_orientation_classify=False, use_doc_unwarping=False)
        # Fixed 3.6.1 pipeline: initialize only VLM on GPU, then attach the official
        # layout predictor on CPU so the 8GB card does not hold both allocators.
        internal = self.pipeline.paddlex_pipeline._pipeline
        layout = config['SubModules']['LayoutDetection']
        internal.layout_det_model = create_predictor(model_name=layout['model_name'],
            model_dir=str(cache / 'PP-DocLayoutV3'), device='cpu', batch_size=1,
            threshold=layout['threshold'], layout_nms=layout['layout_nms'],
            layout_unclip_ratio=layout['layout_unclip_ratio'],
            layout_merge_bboxes_mode=layout['layout_merge_bboxes_mode'])
        internal.use_layout_detection = True
        # Fixed PaddleX 3.6.1 native API: observe generated IDs before text postprocessing.
        predictor = self.pipeline.paddlex_pipeline.vl_rec_model
        model = predictor.infer
        # HF conversion leaves large unused pools. On an 8GB WDDM card they can
        # trigger severe system-memory fallback before the first real request.
        paddle.device.cuda.empty_cache()
        from collections import Counter
        diagnostic = {'event': 'model_memory',
            'parameter_dtypes': dict(Counter(str(p.dtype) for p in model.parameters())),
            'allocated_bytes': paddle.device.cuda.memory_allocated(),
            'reserved_bytes': paddle.device.cuda.memory_reserved(),
            'allocator': paddle.get_flags(['FLAGS_allocator_strategy', 'FLAGS_initial_gpu_memory_in_mb'])}
        print(json.dumps(diagnostic), flush=True)
        generate = model.generate
        eos = predictor.processor.tokenizer.eos_token_id
        eos = {eos} if isinstance(eos, int) else set(eos)

        def observed(inputs, **kwargs):
            output = generate(inputs, **kwargs)
            rows = output[0].numpy().tolist()
            limit = kwargs.get('max_new_tokens', 8192)
            for row in rows:
                ended = any(token in eos for token in row)
                self.generations.append({'tokens': len(row), 'hit_limit': len(row) >= limit and not ended})
            return output

        model.generate = observed
        paddle.device.synchronize()
        self.ready = True
        print(json.dumps({'event': 'ready', 'identity': self.identity}), flush=True)

    def infer(self, data, maximum):
        import paddle
        from PIL import Image
        import numpy as np
        # Paddle's dynamic-graph guard is thread-local. HTTP threads do not inherit
        # the model-loader thread's guard, even though the weights are shared.
        paddle.disable_static()
        paddle.set_device('gpu:0')
        with Image.open(io.BytesIO(data)) as image:
            if image.format != 'PNG' or image.width * image.height > 8000000:
                raise ValueError('INVALID_IMAGE')
            image.load()
            pixels = np.asarray(image.convert('RGB'))[:, :, ::-1].copy()
        self.generations = []
        try:
            results = list(self.pipeline.predict_iter(input=pixels, max_new_tokens=maximum))
        finally:
            paddle.device.cuda.empty_cache()
        if len(results) != 1:
            raise ValueError('INVALID_PAGE_COUNT')
        raw = results[0].json
        raw = raw.get('res', raw)
        # File paths are service internals, not a source identity.
        raw.pop('input_path', None)
        warnings = ['document_blocking_output_truncated'] if any(
            row['hit_limit'] for row in self.generations) else []
        return {'errorCode': 0, 'identity': self.identity, 'warnings': warnings,
                'generation': self.generations,
                'result': {'layoutParsingResults': [{'prunedResult': raw}]}}


def handler(runtime, key):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = 'HTTP/1.1'

        def log_message(self, *args):
            pass  # Never log uploaded text, images, authorization or arbitrary paths.

        def send(self, status, body):
            encoded = json.dumps(body, ensure_ascii=False, allow_nan=False).encode('utf8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(encoded)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(encoded)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self):
            return hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + key)

        def do_GET(self):
            if self.path == '/health':
                return self.send(200, {'alive': True})
            if self.path != '/ready':
                return self.send(404, {'errorCode': 'NOT_FOUND'})
            if not self.authorized():
                return self.send(401, {'errorCode': 'AUTH_REQUIRED'})
            return self.send(200 if runtime.ready else 503,
                             {'ready': runtime.ready, 'identity': runtime.identity})

        def do_POST(self):
            if self.path != '/layout-parsing':
                return self.send(404, {'errorCode': 'NOT_FOUND'})
            if not self.authorized():
                return self.send(401, {'errorCode': 'AUTH_REQUIRED'})
            if not runtime.ready:
                return self.send(503, {'errorCode': 'NOT_READY'})
            # One gate for all clients/Workers, including disconnected timed-out requests.
            if not runtime.gate.acquire(blocking=False):
                return self.send(429, {'errorCode': 'GPU_BUSY'})
            request_id = uuid.uuid4().hex
            started = time.monotonic()
            try:
                self.connection.settimeout(30)
                size = int(self.headers.get('Content-Length', '0'))
                if self.headers.get('Transfer-Encoding') or not 0 < size <= MAX_BODY:
                    return self.send(413, {'errorCode': 'INPUT_TOO_LARGE'})
                payload = json.loads(self.rfile.read(size))
                if (set(payload) != {'file', 'fileType', 'maxNewTokens', 'expectedRevision'}
                        or payload['fileType'] != 1 or type(payload['maxNewTokens']) is not int
                        or not 256 <= payload['maxNewTokens'] <= 8192):
                    raise ValueError('INVALID_INPUT')
                if payload['expectedRevision'] != runtime.identity['revision']:
                    return self.send(409, {'errorCode': 'REVISION_MISMATCH'})
                data = base64.b64decode(payload['file'], validate=True)
                if not 24 <= len(data) <= 20000000 or not data.startswith(b'\x89PNG\r\n\x1a\n'):
                    raise ValueError('INVALID_IMAGE')
                finished = threading.Event()
                def watchdog():
                    if not finished.is_set():
                        print(json.dumps({'event': 'inference_hard_timeout', 'request_id': request_id}), flush=True)
                        os._exit(124)  # Compose restarts this single-request service and releases GPU memory.
                timer = threading.Timer(300, watchdog)
                timer.daemon = True
                timer.start()
                try:
                    result = runtime.execute(data, payload['maxNewTokens'])
                finally:
                    finished.set()
                    timer.cancel()
                result['logId'] = request_id
                self.send(200, result)
                print(json.dumps({'event': 'inference', 'request_id': request_id,
                                  'seconds': round(time.monotonic() - started, 3)}), flush=True)
            except (ValueError, TypeError, KeyError, OSError) as exc:
                print(json.dumps({'event': 'invalid_input_or_result', 'request_id': request_id,
                    'type': type(exc).__name__,
                    'frames': [Path(frame.filename).name + ':' + str(frame.lineno)
                               for frame in traceback.extract_tb(exc.__traceback__)]}), flush=True)
                self.send(400, {'errorCode': 'INVALID_INPUT', 'logId': request_id})
            except Exception as exc:
                oom = 'OutOfMemory' in type(exc).__name__ or 'out of memory' in str(exc).lower()
                if oom:
                    runtime.ready = False  # Explicit restart after OOM; never claim recovery.
                self.send(507 if oom else 500, {'errorCode': 'GPU_OOM' if oom else 'INFERENCE_FAILED', 'logId': request_id})
                print(json.dumps({'event': 'inference_failed', 'request_id': request_id, 'oom': oom}), flush=True)
            finally:
                runtime.gate.release()
    return Handler


def main():
    key_file = os.getenv('PADDLEOCR_API_KEY_FILE', '/run/secrets/paddleocr_api_key')
    key = Path(key_file).read_text().strip()
    if len(key) < 24:
        raise RuntimeError('API_KEY_REQUIRED')
    runtime = Runtime()
    def load():
        try:
            runtime.load()
        except Exception as exc:
            print(json.dumps({'event': 'startup_failed', 'type': type(exc).__name__}), flush=True)
    server = ThreadingHTTPServer(('0.0.0.0', 8080), handler(runtime, key))
    runtime.executor.submit(load)
    server.serve_forever()


if __name__ == '__main__':
    main()
