"""Canonical cross-backend values and fail-closed archive admission."""
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import hashlib
import json

from tools.database_transfer import canonical_value, decode_value, validate_archive, TransferError, content_digest


class TransferContractTests(unittest.TestCase):
    def test_money_json_uuid_and_datetime_keep_their_meaning(self):
        self.assertEqual(canonical_value(Decimal('28.1100'), 'decimal'), '28.1100')
        self.assertEqual(canonical_value('{"b":2,"a":1}', 'json'), {'a':1,'b':2})
        self.assertEqual(canonical_value('12345678123442348234123456789012','uuid'),
                         '12345678-1234-4234-8234-123456789012')
        self.assertEqual(canonical_value(datetime(2026,1,2,3,4,5),'datetime'),
                         canonical_value(datetime(2026,1,2,3,4,5,tzinfo=timezone.utc),'datetime'))
        self.assertIsNone(canonical_value(None,'decimal'))

    def test_boolean_and_vector_roundtrip_are_not_string_coercion(self):
        self.assertIs(canonical_value(0,'bool'),False)
        self.assertEqual(canonical_value('[0.25, 1]','vector'),[0.25,1])
        self.assertEqual(decode_value([0.25,1],'vector'),'[0.25,1]')

    def test_missing_or_incomplete_archive_is_rejected(self):
        with TemporaryDirectory() as folder:
            with self.assertRaises(TransferError):validate_archive(Path(folder))

    def test_unknown_value_kind_is_rejected(self):
        with self.assertRaises(TransferError):canonical_value('a','sql')

    def test_modified_archive_rows_are_rejected_before_import(self):
        with TemporaryDirectory() as folder:
            path=Path(folder);data=b'[1]\n'
            table={'table':'fixture','columns':[{'name':'id','kind':'scalar'}],
                   'rows':1,'content_sha256':content_digest([[1]]),
                   'file_sha256':hashlib.sha256(data).hexdigest()}
            (path/'fixture.jsonl').write_bytes(data)
            (path/'manifest.json').write_text(json.dumps({'format':1,'complete':True,'tables':[table]}))
            self.assertEqual(validate_archive(path)['tables'][0]['rows'],1)
            (path/'fixture.jsonl').write_bytes(b'[2]\n')
            with self.assertRaises(TransferError):validate_archive(path)
