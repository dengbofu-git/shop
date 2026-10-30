"""Start the independent MCP service before web traffic is accepted."""
from django.core.management.base import BaseCommand, CommandError
from support_ai.mcp_lifecycle import start_service, stop_service


class Command(BaseCommand):
    requires_system_checks=[]
    requires_migrations_checks=False

    def add_arguments(self,parser):
        parser.add_argument('--port',type=int,default=18082)
        parser.add_argument('--workers',type=int,default=2)

    def handle(self,*args,**options):
        try:
            process,_=start_service(options['port'],options['workers'])
        except ValueError as exc:
            raise CommandError(str(exc)) from None
        try:
            code=process.wait()
            if code:
                raise CommandError('MCP service stopped unsuccessfully')
        except KeyboardInterrupt:
            pass
        finally:
            stop_service(process)
