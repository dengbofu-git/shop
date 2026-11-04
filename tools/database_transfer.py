"""Offline, loss-checked transfer into a newly prepared PostgreSQL database.

Archives contain private application data. Keep them outside version control.
Existing offline archives require a fresh target database and a preparation token.
"""
import argparse
import base64
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid


class TransferError(RuntimeError):
    pass


KINDS = {'scalar','decimal','datetime','date','uuid','json','vector','bool','bytes'}


def canonical_value(value, kind):
    if kind not in KINDS:
        raise TransferError('Unsupported value kind')
    if value is None:
        return None
    if kind == 'decimal':
        return format(Decimal(value), 'f')
    if kind == 'datetime':
        value = datetime.fromisoformat(value) if isinstance(value, str) else value
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat(timespec='microseconds')
    if kind == 'date':
        return value if isinstance(value, str) else value.isoformat()
    if kind == 'uuid':
        return str(uuid.UUID(str(value)))
    if kind in ('json','vector'):
        if isinstance(value, str):
            return json.loads(value)
        return value.tolist() if hasattr(value, 'tolist') else value
    if kind == 'bool':
        if value not in (True, False, 0, 1):
            raise TransferError('Invalid boolean')
        return bool(value)
    if kind == 'bytes':
        return base64.b64encode(bytes(value)).decode('ascii')
    return value


def decode_value(value, kind):
    if value is None:
        return None
    if kind in ('json','vector'):
        return json.dumps(value, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    if kind == 'decimal':
        return Decimal(value)
    if kind == 'datetime':
        return datetime.fromisoformat(value)
    if kind == 'date':
        return date.fromisoformat(value)
    if kind == 'bytes':
        return base64.b64decode(value, validate=True)
    return value


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf-8')


def content_digest(rows):
    # Independent of backend collation and physical row order; duplicate rows count.
    digests = sorted(hashlib.sha256(encoded(row)).hexdigest() for row in rows)
    return hashlib.sha256(''.join(digests).encode('ascii')).hexdigest()


def validate_archive(folder):
    folder = Path(folder).resolve()
    try:
        manifest = json.loads((folder/'manifest.json').read_text(encoding='utf-8'))
        if manifest['format'] != 1 or manifest['complete'] is not True:
            raise ValueError()
        if not isinstance(manifest['tables'], list) or not manifest['tables']:
            raise ValueError()
        names = set()
        for table in manifest['tables']:
            name = table['table']
            if not re.fullmatch('[a-z][a-z0-9_]{0,100}', name) or name in names or name == 'django_migrations':
                raise ValueError()
            names.add(name)
            file = folder/(name+'.jsonl')
            if file.is_symlink() or file.resolve().parent != folder:
                raise ValueError()
            data = file.read_bytes()
            if hashlib.sha256(data).hexdigest() != table['file_sha256']:
                raise ValueError()
            columns = table['columns']
            if not columns or len({c['name'] for c in columns}) != len(columns):
                raise ValueError()
            if any(c['kind'] not in KINDS for c in columns):
                raise ValueError()
            rows = [json.loads(line) for line in data.splitlines()]
            if any(not isinstance(row,list) or len(row)!=len(columns) for row in rows):
                raise ValueError()
            if len(rows) != table['rows'] or content_digest(rows) != table['content_sha256']:
                raise ValueError()
        return manifest
    except (OSError, ValueError, KeyError, TypeError):
        raise TransferError('Archive is missing, incomplete, invalid or modified') from None


def model_tables():
    from django.apps import apps
    return {m._meta.db_table:m for m in apps.get_models(include_auto_created=True)
            if m._meta.managed and not m._meta.proxy}


def describe(model):
    columns = []
    for field in model._meta.local_fields:
        actual = field.target_field if field.is_relation else field
        internal = actual.get_internal_type()
        kind = {'DecimalField':'decimal','DateTimeField':'datetime','DateField':'date',
                'UUIDField':'uuid','JSONField':'json','VectorField':'vector',
                'BooleanField':'bool','BinaryField':'bytes'}.get(internal,'scalar')
        entry = {'name':field.column,'kind':kind}
        if kind == 'decimal':
            entry['scale'] = actual.decimal_places
        columns.append(entry)
    return columns


def read_rows(connection, table):
    columns = table['columns']
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute('SELECT '+','.join(quote(c['name']) for c in columns)+' FROM '+quote(table['table']))
        rows = []
        for raw in cursor:
            row = []
            for value,column in zip(raw,columns):
                if value is not None and column['kind']=='decimal':
                    original = Decimal(value)
                    if not original.is_finite():
                        raise TransferError('Nonfinite decimal in source')
                    value = original.quantize(Decimal(1).scaleb(-column['scale']))
                    if value != original:
                        raise TransferError('Decimal exceeds target scale; refusing rounding')
                row.append(canonical_value(value,column['kind']))
            rows.append(row)
        return rows


def snapshot(connection, tables):
    return {t['table']:{'rows':len(rows),'sha256':content_digest(rows)}
            for t in tables for rows in [read_rows(connection,t)]}


def target_connection():
    from django.conf import settings
    from django.db import connections
    if settings.AI_STORAGE_DB_ALIAS != 'default' or set(settings.DATABASES) != {'default'}:
        raise TransferError('Target requires the single default connection')
    connection = connections['default']
    if connection.vendor != 'postgresql':
        raise TransferError('Target must be PostgreSQL')
    name = connection.settings_dict['NAME']
    if not re.fullmatch('tea_saas_unified_[a-z0-9_]{1,55}',name):
        raise TransferError('Target name must be an explicit tea_saas_unified_* migration database')
    return connection


def prepare_target():
    from django.core.management import call_command
    connection = target_connection()
    with connection.cursor() as cursor:
        if connection.introspection.table_names(cursor):
            raise TransferError('Refusing to prepare a nonempty target database')
    call_command('migrate',database='default',interactive=False,verbosity=0)
    tables = [{'table':name,'columns':describe(model)} for name,model in sorted(model_tables().items())]
    baseline = snapshot(connection,tables)
    token = str(uuid.uuid4())
    with connection.cursor() as cursor:
        cursor.execute('CREATE SCHEMA tea_saas_transfer')
        cursor.execute('CREATE TABLE tea_saas_transfer.receipt (id integer PRIMARY KEY CHECK (id=1), '
                       'token uuid NOT NULL, state text NOT NULL, baseline jsonb NOT NULL, archive_sha256 text)')
        cursor.execute('INSERT INTO tea_saas_transfer.receipt VALUES (1,%s,%s,%s,NULL)',
                       [token,'prepared',json.dumps(baseline)])
    return {'target':connection.settings_dict['NAME'],'token':token,'tables':len(tables),'state':'prepared'}


def ordered_tables(tables):
    pending = {t['table']:t for t in tables}
    result = []
    while pending:
        ready = [name for name,t in pending.items() if not set(t['dependencies']) & pending.keys()]
        if not ready:
            raise TransferError('Cyclic table dependencies require an explicit transfer design')
        for name in sorted(ready):
            result.append(pending.pop(name))
    return result


REVISION_TRIGGERS = [('ai_storage_knowledgechunk','ai_chunks_revision'),
                     ('ai_storage_knowledgedocument','ai_documents_revision'),
                     ('ai_storage_embeddingspace','ai_spaces_revision')]


def import_archive(folder, token):
    from django.db import transaction
    from psycopg2.extras import execute_values
    folder = Path(folder).resolve()
    manifest = validate_archive(folder)
    connection = target_connection()
    models = model_tables()
    tables = manifest['tables']
    if {t['table'] for t in tables} != set(models):
        raise TransferError('Archive model coverage differs from target')
    for table in tables:
        if table['columns'] != describe(models[table['table']]):
            raise TransferError('Archive column contract differs from target')
    expected = {t['table']:{'rows':t['rows'],'sha256':t['content_sha256']} for t in tables}
    archive_sha = hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest()
    quote = connection.ops.quote_name
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT token::text,state,baseline FROM tea_saas_transfer.receipt WHERE id=1 FOR UPDATE')
            receipt = cursor.fetchone()
            if not receipt or receipt[0]!=token or receipt[1]!='prepared':
                raise TransferError('Target receipt does not permit an import')
            # Prevent a concurrent commit between baseline check and TRUNCATE.
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute('LOCK TABLE '+','.join(quote(t['table']) for t in sorted(tables,key=lambda t:t['table']))+' IN ACCESS EXCLUSIVE MODE')
            baseline = json.loads(receipt[2]) if isinstance(receipt[2],str) else receipt[2]
            if snapshot(connection,tables) != baseline:
                raise TransferError('Target changed after preparation; refusing overwrite')
            cursor.execute('SET CONSTRAINTS ALL DEFERRED')
            # Derived invalidation epochs must not change source field values.
            # FK triggers and embedding guards stay enabled throughout the load.
            for table,trigger in REVISION_TRIGGERS:
                cursor.execute('ALTER TABLE '+quote(table)+' DISABLE TRIGGER '+quote(trigger))
            cursor.execute('TRUNCATE '+','.join(quote(t['table']) for t in tables)+' RESTART IDENTITY')
            for table in ordered_tables(tables):
                rows = [json.loads(line) for line in (folder/(table['table']+'.jsonl')).read_bytes().splitlines()]
                columns = table['columns']
                values = [tuple(decode_value(v,c['kind']) for v,c in zip(row,columns)) for row in rows]
                if values:
                    sql = 'INSERT INTO '+quote(table['table'])+' ('+','.join(quote(c['name']) for c in columns)+') VALUES %s'
                    execute_values(cursor.cursor,sql,values,page_size=500)
            # Drain deferred FK events before ALTER TABLE. PostgreSQL refuses
            # trigger changes on a relation with pending deferred events.
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            for table,trigger in REVISION_TRIGGERS:
                cursor.execute('ALTER TABLE '+quote(table)+' ENABLE TRIGGER '+quote(trigger))
            for table,model in models.items():
                pk = model._meta.pk
                if pk.get_internal_type() not in ('AutoField','BigAutoField','SmallAutoField'):
                    continue
                cursor.execute('SELECT pg_get_serial_sequence(%s,%s)',[table,pk.column])
                sequence = cursor.fetchone()[0]
                if sequence:
                    cursor.execute('SELECT setval(%s::regclass,COALESCE(MAX('+quote(pk.column)+'),1),MAX('+quote(pk.column)+') IS NOT NULL) FROM '+quote(table),[sequence])
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            actual = snapshot(connection,tables)
            if actual != expected:
                differing = [name for name in expected if actual[name]!=expected[name]]
                raise TransferError('Transferred content differs for tables: '+','.join(differing))
            cursor.execute('UPDATE tea_saas_transfer.receipt SET state=%s,archive_sha256=%s WHERE id=1',
                           ['applied',archive_sha])
    return {'tables_verified':len(tables),'rows_verified':sum(t['rows'] for t in tables),
            'content_equal':True,'archive_sha256':archive_sha,'state':'applied'}


def verify_target(folder):
    manifest = validate_archive(folder)
    actual = snapshot(target_connection(),manifest['tables'])
    expected = {t['table']:{'rows':t['rows'],'sha256':t['content_sha256']} for t in manifest['tables']}
    if actual != expected:
        raise TransferError('Target no longer equals archive')
    return {'content_equal':True,'tables_verified':len(expected)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=['prepare','import','verify'])
    parser.add_argument('--archive',type=Path)
    parser.add_argument('--token')
    args = parser.parse_args()
    if args.operation != 'prepare' and args.archive is None:
        parser.error('--archive is required')
    if args.operation == 'import' and args.token is None:
        parser.error('--token is required')
    import os
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    os.environ.setdefault('DJANGO_SETTINGS_MODULE','tea_saas.settings')
    import django
    django.setup()
    operations = {'prepare':prepare_target,
                  'import':lambda:import_archive(args.archive,args.token),'verify':lambda:verify_target(args.archive)}
    try:
        print(json.dumps(operations[args.operation](),ensure_ascii=False))
    except TransferError as error:
        parser.exit(1,'Transfer refused: '+str(error)+'\n')
    except Exception as error:
        # Backend exceptions can embed real row contents or credentials.
        parser.exit(1,'Transfer failed: '+type(error).__name__+'; private details suppressed\n')


if __name__ == '__main__':
    main()
