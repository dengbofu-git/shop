"""Bounded application streams: progress and verified units, never model drafts."""
import json
import queue
import threading
import time
import logging
from contextlib import contextmanager
from contextvars import ContextVar, copy_context

from django.db import close_old_connections
from django.http import StreamingHttpResponse

_sink = ContextVar('support_stream_sink',default=None)
_slots = threading.BoundedSemaphore(8)
logger = logging.getLogger(__name__)
LABELS = {
    'accepted':'已收到问题，正在处理…', 'context':'正在理解您的问题…',
    'planning':'正在整理处理步骤…', 'history':'正在读取本次咨询的上下文…',
    'preferences':'正在读取您保存的偏好…', 'retrieval':'正在查找相关资料…',
    'generation':'正在整理回答…', 'verification':'正在核对回答依据…',
    'products':'正在匹配符合条件的商品…', 'orders':'正在查询订单…',
    'details':'正在读取商品信息…', 'compliance':'正在检查回答…',
    'saving':'正在保存本轮咨询…', 'complete':'回答已完成。',
}


class StreamCancelled(RuntimeError):
    pass


def checkpoint():
    sink=_sink.get()
    if sink and sink.cancelled.is_set():
        raise StreamCancelled('Stream closed')


def cancellation_callback():
    """Interrupt provider streaming at token boundaries without exposing drafts."""
    if _sink.get() is None:
        return None
    from langchain_core.callbacks import BaseCallbackHandler
    class CancelOnDisconnect(BaseCallbackHandler):
        raise_error = True
        def on_llm_new_token(self, token, **kwargs):
            checkpoint()
    return CancelOnDisconnect()


def progress(stage):
    checkpoint()
    sink=_sink.get()
    if sink and stage in LABELS:
        sink.progress(stage)


def verified_result(result, order):
    """Only registered server facts or independently grounded knowledge qualify."""
    sink=_sink.get()
    if sink is None:
        return
    checkpoint()
    from .business_grounding import needs_model_review, make_answer_block
    from .pii import contains_pii
    if needs_model_review([result]):
        return
    text=make_answer_block(result)['text']
    if contains_pii(text):
        return
    sink.blocks[result['step_id']]=text
    text='\n\n'.join(sink.blocks[key] for key in order if key in sink.blocks)
    sink.put('answer',{'text':text,'provisional':True})


@contextmanager
def bind_stream(sink):
    token=_sink.set(sink)
    try:
        yield sink
    finally:
        _sink.reset(token)


class EventSink:
    def __init__(self):
        self.queue=queue.Queue(maxsize=32)
        self.cancelled=threading.Event()
        self.finished=threading.Event()
        self.started=time.monotonic()
        self.blocks={}
        self.stage=None
        self.result=None

    def put(self,event,data):
        if self.cancelled.is_set():
            raise StreamCancelled('Stream closed')
        try:
            self.queue.put_nowait((event,data))
        except queue.Full:
            pass  # Progress/snapshots may coalesce; the terminal result cannot.

    def progress(self,stage):
        if stage==self.stage:
            return
        self.stage=stage
        self.put('status',{'stage':stage,'message':LABELS[stage]})


def frame(event,data):
    return ('event: '+event+'\ndata: '+json.dumps(data,ensure_ascii=False,allow_nan=False)+'\n\n').encode('utf-8')


def event_response(request,run):
    """Run once in a bounded worker. Disconnect cancels future checkpoints."""
    if not _slots.acquire(blocking=False):
        return None
    sink=EventSink()
    context=copy_context()
    request._support_stream_context={}

    def work():
        close_old_connections()
        try:
            with bind_stream(sink):
                response=run()
            data=json.loads(response.content)
            sink.result=(response.status_code,data)
            from tea_saas.runtime_logging import request_context
            log_context=request_context.get() or {}
            request._support_stream_context.update(http_status=response.status_code,
                trace_id=data.get('trace_id') or log_context.get('trace_id',''),
                span_id=log_context.get('span_id',''))
        except StreamCancelled:
            sink.result=(499,{'error':'本轮连接已关闭。','error_code':'CANCELLED','retryable':True})
            request._support_stream_context['http_status']=499
        except Exception:
            logger.exception('support.workflow.failed')
            sink.result=(503,{'error':'智能客服暂时无法响应，请稍后重试。',
                              'error_code':'STREAM_EXECUTION_FAILED','retryable':True})
            request._support_stream_context['http_status']=503
        finally:
            try:
                close_old_connections()
            finally:
                sink.finished.set()
                try:
                    sink.queue.put_nowait((None, None))
                except queue.Full:
                    pass
                _slots.release()

    thread=threading.Thread(target=lambda:context.run(work),daemon=True,name='support-stream')
    started=False

    def events():
        nonlocal started
        try:
            # This frame is yielded before graph/model imports or tool work.
            yield frame('status',{'stage':'accepted','message':LABELS['accepted']})
            started=True
            try:
                thread.start()
            except Exception:
                _slots.release()
                raise
            while not sink.finished.is_set() or not sink.queue.empty():
                try:
                    event,data=sink.queue.get(timeout=.25)
                    if event is not None:
                        yield frame(event,data)
                except queue.Empty:
                    if sink.finished.is_set():
                        break
                    now=time.monotonic()
                    if now-events.last_ping>=5:
                        events.last_ping=now
                        yield frame('ping',{'elapsed_seconds':round(now-sink.started,1)})
            status,data=sink.result
            if status>=400:
                yield frame('error',dict(data,status=status))
            else:
                # Final authoritative replacement also covers fixed replies and
                # idempotent replay. No artificial character delays or LLM call.
                yield frame('answer',{'text':data['answer'],'provisional':False})
                yield frame('done',data)
        finally:
            sink.cancelled.set()
    events.last_ping=time.monotonic()

    response=StreamingHttpResponse(events(),content_type='text/event-stream; charset=utf-8')
    response['Cache-Control']='no-store, no-transform'
    response['X-Accel-Buffering']='no'

    def closed():
        sink.cancelled.set()
        if not started:
            _slots.release()
    response._resource_closers.append(closed)
    return response
