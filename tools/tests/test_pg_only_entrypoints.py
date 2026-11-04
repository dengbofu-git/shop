"""Retired database entrypoints must not restart a legacy backend."""
from pathlib import Path
import subprocess
import sys
import unittest

ROOT=Path(__file__).resolve().parents[2]


class PostgreSQLOnlyEntrypoints(unittest.TestCase):
    def test_mcp_fixture_help_has_no_legacy_database_launcher(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/tea_saas_mcp/agent_integration.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertNotIn('--mysql',result.stdout)

    def test_transfer_only_accepts_existing_offline_archives(self):
        result=subprocess.run([sys.executable,str(ROOT/'tools/database_transfer.py'),'--help'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0)
        self.assertNotIn('export',result.stdout)

    def test_no_optional_legacy_runtime_dependency_file(self):
        self.assertFalse((ROOT/'tools/database-transfer-requirements.txt').exists())

    def test_no_retired_database_settings_entrypoints(self):
        for name in ('goods/test_mysql_settings.py','engagement/test_mysql_settings.py'):
            self.assertFalse((ROOT/name).exists(),name)
