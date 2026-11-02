"""Real two-connection race against the import admission boundary, synthetic data."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch
import uuid

from django.db import connection, connections, OperationalError
from django.test import TransactionTestCase
from ai_storage.database import alias
from users.models import UserProfile
from tools import database_transfer as transfer


@skipUnless(alias() == 'default' and connection.vendor == 'postgresql', 'requires unified PostgreSQL')
class TransferWriteRaceTests(TransactionTestCase):
    def test_baseline_check_excludes_a_racing_target_writer(self):
        self.assertTrue(connection.settings_dict['NAME'].startswith('test_'))
        UserProfile.objects.create(username='guardseed', is_active=True)
        models=transfer.model_tables();tables=[]
        with TemporaryDirectory() as folder:
            folder=Path(folder)
            for name,model in models.items():
                table={'table':name,'columns':transfer.describe(model),'dependencies':sorted({
                    f.remote_field.model._meta.db_table for f in model._meta.local_fields
                    if f.is_relation and f.remote_field.model is not model})}
                rows=transfer.read_rows(connection,table)
                data=b''.join(transfer.encoded(row)+b'\n' for row in rows)
                (folder/(name+'.jsonl')).write_bytes(data)
                table.update(rows=len(rows),file_sha256=hashlib.sha256(data).hexdigest(),content_sha256=transfer.content_digest(rows))
                tables.append(table)
            (folder/'manifest.json').write_bytes(transfer.encoded({'format':1,'complete':True,'tables':tables}))
            baseline=transfer.snapshot(connection,tables);token=str(uuid.uuid4())
            with connection.cursor() as cursor:
                cursor.execute('CREATE SCHEMA tea_saas_transfer')
                cursor.execute('CREATE TABLE tea_saas_transfer.receipt (id integer PRIMARY KEY, token uuid, state text, baseline jsonb, archive_sha256 text)')
                cursor.execute('INSERT INTO tea_saas_transfer.receipt VALUES (1,%s,%s,%s,NULL)',[token,'prepared',json.dumps(baseline)])
            self.addCleanup(self.drop_test_receipt)
            def writer():
                connections.close_all()
                try:
                    with connections['default'].cursor() as cursor:cursor.execute("SET lock_timeout = '150ms'")
                    UserProfile.objects.create(username='guardrace',is_active=True)
                    return 'committed'
                except OperationalError as error:
                    return error.__cause__.pgcode
                finally:connections.close_all()
            original=transfer.snapshot;writer_result=[]
            def observe_baseline(conn,items):
                result=original(conn,items)
                if not writer_result:
                    with ThreadPoolExecutor(max_workers=1) as pool:
                        writer_result.append(pool.submit(writer).result(timeout=5))
                return result
            with patch.object(transfer,'target_connection',return_value=connection),patch.object(transfer,'snapshot',side_effect=observe_baseline):
                self.assertEqual(transfer.import_archive(folder,token)['state'],'applied')
            self.assertEqual(writer_result,['55P03'])
            self.assertTrue(UserProfile.objects.filter(username='guardseed').exists())
            self.assertFalse(UserProfile.objects.filter(username='guardrace').exists())

    @staticmethod
    def drop_test_receipt():
        with connection.cursor() as cursor:cursor.execute('DROP SCHEMA IF EXISTS tea_saas_transfer CASCADE')
