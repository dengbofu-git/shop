"""Local development: warm the owned MCP service before launching the web server."""
import os
import subprocess
import sys
import time
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from support_ai.mcp_lifecycle import start_service, stop_service, wait_ready


class Command(BaseCommand):
    requires_system_checks=[]
    requires_migrations_checks=False

    def add_arguments(self,parser):
        parser.add_argument('--addrport',default='127.0.0.1:8000')
        parser.add_argument('--mcp-port',type=int,default=18082)
        parser.add_argument('--mcp-workers',type=int,default=2)

    def handle(self,*args,**options):
        import django
        if sys.version_info[:2] != (3,13) or django.VERSION[:2] != (5,2):
            raise CommandError('Python 3.13 / Django 5.2 is required; legacy startup is disabled')
        url=urlsplit(settings.SUPPORT_MCP_URL)
        if (settings.SUPPORT_MCP_TRANSPORT!='http' or url.scheme!='http' or url.hostname!='127.0.0.1' or
                url.port!=options['mcp_port'] or url.path!='/mcp' or url.username or url.password or url.query or url.fragment):
            raise CommandError('SUPPORT_MCP_URL must match this launcher loopback port and HTTP transport')
        process,web=None,None
        try:
            process,instance=start_service(options['mcp_port'],options['mcp_workers'])
            wait_ready(process,instance,options['mcp_port'])
            self.stdout.write('MCP workers ready; starting local web server.')
            web=subprocess.Popen([sys.executable,'-u',str(settings.BASE_DIR/'manage.py'),'runserver',
                options['addrport'],'--noreload'],cwd=str(settings.BASE_DIR),env=dict(os.environ))
            while web.poll() is None:
                if process.poll() is not None:
                    raise RuntimeError('Owned MCP service stopped')
                time.sleep(.2)
            if web.returncode:
                raise RuntimeError('Local web server stopped unsuccessfully')
        except KeyboardInterrupt:
            pass
        except (ValueError,RuntimeError) as exc:
            raise CommandError(str(exc)) from None
        finally:
            try:
                if web is not None and web.poll() is None:
                    web.terminate()
                    try:
                        web.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        web.kill()
                        web.wait(timeout=5)
            finally:
                if process is not None:
                    stop_service(process)
