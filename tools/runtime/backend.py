"""Single Python 3.13 / Django 5.2 entry point for the local Web + warm MCP service."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]


def check_schema(*, profile=False):
    """Read-only readiness; a worker cannot race ahead of reviewed migrations."""
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from django.db.migrations.executor import MigrationExecutor
    if profile:
        from ai_storage.database import alias as ai_alias
        if (set(connections) != {'default'} or ai_alias() != 'default'
                or connections['default'].vendor != 'postgresql'):
            raise RuntimeError('Profile worker requires one default PostgreSQL connection')
    call_command('check')
    for alias in connections:
        connection = connections[alias]
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                assert cursor.fetchone()[0] == 1
            executor = MigrationExecutor(connection)
            executor.loader.check_consistent_history(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            if plan:
                pending = ', '.join(f'{migration.app_label}.{migration.name}' for migration, _ in plan)
                raise RuntimeError(
                    f'Database {alias} has unapplied migrations: {pending}. '
                    'Runtime preflight is read-only; apply reviewed migrations separately before restart.'
                )
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=ROOT / '.env')
    parser.add_argument('--postgres-env-file', type=Path, default=ROOT / '.env.postgres')
    parser.add_argument('--runtime-env', type=Path, default=ROOT / '.scratch/runtime/service.env')
    parser.add_argument('--media-root', type=Path)
    parser.add_argument('--addrport', default='127.0.0.1:8000')
    parser.add_argument('--mcp-port', type=int, default=18082)
    parser.add_argument('--mcp-workers', type=int, default=2)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--profile-status', action='store_true')
    mode.add_argument('--profile-worker', action='store_true')
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
    if args.profile_status:
        from django.conf import settings
        print(json.dumps({'enabled': bool(getattr(settings, 'SUPPORT_AUTO_PROFILE_ENABLED', False))}), flush=True)
    elif args.profile_worker:
        from django.conf import settings
        if not getattr(settings, 'SUPPORT_AUTO_PROFILE_ENABLED', False):
            raise RuntimeError('Automatic profile worker is disabled')
        check_schema(profile=True)
        print('TEA_SAAS_PROFILE_WORKER_READY', flush=True)
        call_command('profile_worker')
    elif args.check:
        check_schema()
        print('Python 3.13 / Django 5.2 checks, database connectivity and migration readiness passed.', flush=True)
    else:
        call_command('run_support_backend', addrport=args.addrport,
                     mcp_port=args.mcp_port, mcp_workers=args.mcp_workers)


if __name__ == '__main__':
    main()
