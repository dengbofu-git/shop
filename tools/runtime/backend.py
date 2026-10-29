"""Single Python 3.13 / Django 5.2 entry point for the local Web + warm MCP service."""
import argparse
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--postgres-env-file', type=Path, default=ROOT / '.env.postgres')
    parser.add_argument('--runtime-env', type=Path, default=ROOT / '.scratch/runtime/service.env')
    parser.add_argument('--media-root', type=Path)
    parser.add_argument('--addrport', default='127.0.0.1:8000')
    parser.add_argument('--mcp-port', type=int, default=18082)
    parser.add_argument('--mcp-workers', type=int, default=2)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 13):
        parser.error('Python 3.13 is required; no legacy runtime fallback is supported.')
    from dotenv import load_dotenv
    if not args.env_file.is_file():
        parser.error('The application env file is missing.')
    load_dotenv(args.env_file, override=False)
    load_dotenv(args.postgres_env_file, override=False)
    load_dotenv(args.runtime_env, override=True)
    if args.media_root:
        os.environ['DJANGO_MEDIA_ROOT'] = str(args.media_root.resolve())
    os.chdir(ROOT)
    sys.path.insert(0, str(ROOT))
    os.environ['PYTHONPATH'] = str(ROOT)
    os.environ['DJANGO_SETTINGS_MODULE'] = 'tea_saas.settings'
    import django
    if django.VERSION[:2] != (5, 2):
        parser.error('Django 5.2 is required.')
    django.setup()
    from django.core.management import call_command
    if args.check:
        call_command('check')
        from django.db import connections
        for alias in ('default', 'ai_storage'):
            with connections[alias].cursor() as cursor:
                cursor.execute('SELECT 1')
                assert cursor.fetchone()[0] == 1
            connections[alias].close()
        print('Python 3.13 / Django 5.2 checks and database connectivity passed.', flush=True)
    else:
        call_command('run_support_backend', addrport=args.addrport,
                     mcp_port=args.mcp_port, mcp_workers=args.mcp_workers)


if __name__ == '__main__':
    main()
