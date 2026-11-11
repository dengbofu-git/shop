"""Synthetic read-retry contract; no database or model service calls."""
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch
from django.db import DatabaseError
from .context import PreferenceStorageUnavailable, saved_preferences
from ai_storage.database import alias as ai_db_alias

def failure(code):
    cause=RuntimeError('synthetic');cause.pgcode=code
    exc=DatabaseError('synthetic');exc.__cause__=cause
    return exc

class PreferenceReadRecoveryTests(TestCase):
    def read(self, errors, atomic=False):
        connection=SimpleNamespace(in_atomic_block=atomic,close=Mock())
        with patch('support_ai.context.connections',{ai_db_alias():connection}), patch('ai_storage.profile_service.read_preferences',side_effect=errors) as query:
            try:result=saved_preferences(SimpleNamespace(pk=1))
            except PreferenceStorageUnavailable as exc:result=exc
        return result,query,connection

    def test_known_transport_break_reconnects_once_then_reads(self):
        result,query,connection=self.read([failure('08006'),None])
        self.assertIsNone(result);self.assertEqual(query.call_count,2);connection.close.assert_called_once_with()

    def test_configuration_failure_does_not_retry_or_hide_missing_memory(self):
        result,query,connection=self.read([failure('28P01')])
        self.assertIsInstance(result,PreferenceStorageUnavailable);self.assertTrue(result.configuration_error)
        self.assertEqual(query.call_count,1);connection.close.assert_not_called()

    def test_persistent_transport_failure_stops_after_second_read(self):
        result,query,connection=self.read([failure('08006'),failure('08006')])
        self.assertIsInstance(result,PreferenceStorageUnavailable);self.assertFalse(result.configuration_error)
        self.assertEqual(query.call_count,2);connection.close.assert_called_once_with()

    def test_inside_transaction_never_reconnects(self):
        result,query,connection=self.read([failure('08006')],atomic=True)
        self.assertIsInstance(result,PreferenceStorageUnavailable);self.assertEqual(query.call_count,1)
        connection.close.assert_not_called()
