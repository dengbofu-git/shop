"""Bounded, prewarmed Django processes; one exclusive lease per signed grant."""
import asyncio
import hashlib
import json
import math
import os
import time
from dataclasses import dataclass
from pathlib import Path

from .server import ROOT, PRIVATE_OUTPUT, private_failure
from jsonschema import validate, ValidationError


class PoolError(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


class Worker:
    def __init__(self, python):
        self.python = python
        self.process = None
        self.lock = asyncio.Lock()
        self.healthy = False

    async def start(self):
        environment = dict(os.environ)
        environment.pop('TEA_SAAS_AGENT_GRANT', None)
        self.process = await asyncio.create_subprocess_exec(
            self.python, '-u', '-X', 'utf8', str(ROOT / 'manage.py'), 'mcp_agent_worker', '--no-color',
            cwd=str(ROOT), env=environment, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, limit=2097152,
            creationflags=0x08000000 if os.name == 'nt' else 0)
        try:
            line = await asyncio.wait_for(self.process.stdout.readline(), 30)
            if line.strip() != b'{"worker_ready":1}':
                raise PoolError('BACKEND_NOT_CONFIGURED')
            self.healthy = True
        except BaseException:
            await self.stop()
            raise

    async def rpc(self, message, timeout=35):
        async with self.lock:
            if not self.healthy:
                raise PoolError('SERVICE_UNAVAILABLE')
            try:
                raw = json.dumps(message, ensure_ascii=False, allow_nan=False).encode('utf-8')
                if len(raw) > 262144:
                    raise PoolError('INVALID_ARGUMENT')
                self.process.stdin.write(raw + b'\n')
                await self.process.stdin.drain()
                line = await asyncio.wait_for(self.process.stdout.readline(), timeout)
                if not line or len(line) > 2097152:
                    raise PoolError('INVALID_BACKEND_RESPONSE')
                return json.loads(line)
            except asyncio.CancelledError:
                await self.stop()
                raise
            except asyncio.TimeoutError:
                await self.stop()
                raise PoolError('BACKEND_TIMEOUT') from None
            except (OSError, ValueError):
                await self.stop()
                raise PoolError('INVALID_BACKEND_RESPONSE') from None

    async def stop(self):
        self.healthy = False
        if self.process is not None and self.process.returncode is None:
            try:
                self.process.kill()
            except ProcessLookupError:
                pass
            await self.process.wait()


@dataclass
class Lease:
    worker: Worker
    expires: float


class WorkerPool:
    def __init__(self, python, size=2, acquire_timeout=2, lease_seconds=120):
        if not Path(python).is_absolute() or not Path(python).is_file() or not 1 <= size <= 16:
            raise ValueError('Invalid worker configuration')
        self.python, self.size = python, size
        self.acquire_timeout, self.lease_seconds = acquire_timeout, min(120, lease_seconds)
        self.available = asyncio.Queue(maxsize=size)
        self.workers, self.leases, self.tasks = set(), {}, set()
        self.returning = set()
        self.open_lock = asyncio.Lock()
        self.stopping = False
        self.reaper = None
        self.startup_ms = 0
        self.worker_starts = 0

    @staticmethod
    def key(grant):
        return hashlib.sha256(grant.encode('utf-8')).hexdigest()

    async def _add_worker(self):
        worker = Worker(self.python)
        self.workers.add(worker)
        try:
            await worker.start()
            self.worker_starts += 1
            if self.stopping:
                await worker.stop()
            else:
                self.available.put_nowait(worker)
        except BaseException:
            self.workers.discard(worker)
            await worker.stop()
            raise

    async def start(self):
        started = time.monotonic()
        try:
            await asyncio.gather(*(self._add_worker() for _ in range(self.size)))
        except BaseException:
            await self.stop()
            raise
        self.startup_ms = round((time.monotonic()-started)*1000, 3)
        self.reaper = asyncio.create_task(self._reap())

    def health(self):
        ready = sum(self._alive(w) for w in self.workers)
        return dict(status='ready' if ready == self.size and not self.stopping else 'degraded',
                    workers=ready, available=self.available.qsize(), active_sessions=len(self.leases),
                    startup_ms=self.startup_ms, worker_starts=self.worker_starts)

    @staticmethod
    def _alive(worker):
        process = getattr(worker,'process',None)
        return worker.healthy and (process is None or process.returncode is None)

    async def open(self, grant):
        key = self.key(grant)
        async with self.open_lock:
            if self.stopping:
                raise PoolError('SERVICE_UNAVAILABLE')
            current = self.leases.get(key)
            if current:
                if time.monotonic() >= current.expires or not self._alive(current.worker):
                    raise PoolError('ACCESS_DENIED')
                return current
            try:
                worker = await asyncio.wait_for(self.available.get(), self.acquire_timeout)
            except asyncio.TimeoutError:
                raise PoolError('BACKEND_BUSY') from None
            try:
                result = await worker.rpc({'action':'open', 'grant':grant}, timeout=5)
                if (not isinstance(result,dict) or result.get('session_ready')!=1 or
                        type(result.get('expires_at')) not in (int,float) or
                        not math.isfinite(result['expires_at']) or
                        not 0 < result['expires_at']-time.time() <= 120):
                    raise PoolError('ACCESS_DENIED')
                lease = Lease(worker, time.monotonic()+min(self.lease_seconds,result['expires_at']-time.time()))
                self.leases[key] = lease
                return lease
            except BaseException:
                await self._return(worker)
                raise

    async def call(self, grant, name, arguments):
        lease = self.leases.get(self.key(grant))
        if lease is None or time.monotonic() >= lease.expires:
            return private_failure('ACCESS_DENIED')
        try:
            result = await lease.worker.rpc({'action':'call', 'tool':name, 'arguments':arguments},
                timeout=max(.001, min(35, lease.expires-time.monotonic())))
            validate(result, PRIVATE_OUTPUT)
            return result
        except PoolError as exc:
            return private_failure(exc.code)
        except (ValueError, ValidationError):
            await lease.worker.stop()
            return private_failure('INVALID_BACKEND_RESPONSE')

    async def _replace(self):
        while not self.stopping:
            try:
                await self._add_worker()
                return
            except Exception:
                await asyncio.sleep(1)

    async def _return(self, worker):
        if worker not in self.workers or worker in self.returning:
            return
        self.returning.add(worker)
        try:
            await self._reset_and_return(worker)
        finally:
            self.returning.discard(worker)

    async def _reset_and_return(self, worker):
        if worker.healthy:
            try:
                result = await asyncio.wait_for(worker.rpc({'action':'close'}, timeout=2), 3)
                if result != {'session_closed':1}:
                    await worker.stop()
            except (PoolError, asyncio.TimeoutError):
                await worker.stop()
        if worker.healthy and not self.stopping:
            self.available.put_nowait(worker)
        else:
            await worker.stop()
            self.workers.discard(worker)
            if not self.stopping:
                task = asyncio.create_task(self._replace())
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)

    async def release(self, grant):
        lease = self.leases.pop(self.key(grant), None)
        if lease:
            await self._return(lease.worker)

    async def _reap(self):
        while True:
            await asyncio.sleep(1)
            # Supervise idle workers proactively, rather than respawning one
            # while a new user request waits for Python/Django imports.
            for _ in range(self.available.qsize()):
                try:
                    worker=self.available.get_nowait()
                except asyncio.QueueEmpty:
                    break
                if self._alive(worker):
                    self.available.put_nowait(worker)
                else:
                    await worker.stop()
                    await self._return(worker)
            for key, lease in list(self.leases.items()):
                if time.monotonic() >= lease.expires:
                    self.leases.pop(key, None)
                    # No expired request may keep running against a reused slot.
                    await lease.worker.stop()
                    await self._return(lease.worker)
                elif not self._alive(lease.worker):
                    # Keep the failed lease bound to the dead worker: an
                    # in-flight request must never acquire fresh counters.
                    await lease.worker.stop()
                    await self._return(lease.worker)

    async def stop(self):
        self.stopping = True
        if self.reaper:
            self.reaper.cancel()
            await asyncio.gather(self.reaper, return_exceptions=True)
        for task in list(self.tasks):
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        await asyncio.gather(*(w.stop() for w in self.workers), return_exceptions=True)
        self.workers.clear()
        self.leases.clear()
