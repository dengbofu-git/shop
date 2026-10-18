"""One bounded JSON response for the local MCP subprocess bridge."""
import json

from django.core.management.base import BaseCommand
from support_ai.product_details import get_product_details


class Command(BaseCommand):
    help = '只读商品公开详情，供本地 MCP 调用；不调用模型、不写会话或足迹。'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--sku-id', type=int, required=True)

    def handle(self, *args, **options):
        try:
            result = get_product_details(options['sku_id'])
        except ValueError:
            result = {'schema_version': '1.0', 'status': 'error', 'data': None,
                      'error_code': 'INVALID_ARGUMENT', 'retryable': False}
        except Exception:
            # No database names, SQL, hostnames, credentials or traceback on stdout.
            result = {'schema_version': '1.0', 'status': 'error', 'data': None,
                      'error_code': 'SERVICE_UNAVAILABLE', 'retryable': True}
        self.stdout.write(json.dumps(result, ensure_ascii=False))
