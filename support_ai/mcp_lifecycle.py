"""Explicit service supervision for local launchers, never called by chat views."""
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import requests
from django.conf import settings


def start_service(port, workers):
    executable=Path(settings.SUPPORT_MCP_PYTHON)
    token=settings.SUPPORT_MCP_SERVICE_TOKEN
    if (not executable.is_absolute() or not executable.is_file() or
            not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',token) or
            not 1024<=port<=65535 or not 1<=workers<=16):
        raise ValueError('Configure the MCP interpreter, service token, loopback port and worker count')
    instance=uuid.uuid4().hex
    environment=dict(os.environ,TEA_SAAS_PYTHON=sys.executable,SUPPORT_MCP_SERVICE_TOKEN=token,
                     TEA_SAAS_MCP_INSTANCE=instance)
    process=subprocess.Popen([str(executable),'-u','-m','tools.tea_saas_mcp.resident',
        '--port',str(port),'--workers',str(workers),'--watch-stdin'],cwd=str(settings.BASE_DIR),
        env=environment,stdin=subprocess.PIPE,start_new_session=os.name!='nt')
    return process,instance


def wait_ready(process,instance,port,timeout=40):
    deadline=time.monotonic()+timeout
    with requests.Session() as client:
        client.trust_env=False
        while process.poll() is None and time.monotonic()<deadline:
            try:
                with client.get('http://127.0.0.1:'+str(port)+'/health',timeout=.5) as response:
                    value=response.json()
                    if response.status_code==200 and value.get('instance_id')==instance:
                        return
            except (requests.RequestException,ValueError):
                pass
            time.sleep(.2)
    raise RuntimeError('The owned MCP service did not become ready')


def stop_service(process):
    if process.stdin:
        process.stdin.close()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        if os.name=='nt':
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        else:
            os.killpg(process.pid,signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            if os.name!='nt':
                os.killpg(process.pid,signal.SIGKILL)
            process.wait(timeout=5)
