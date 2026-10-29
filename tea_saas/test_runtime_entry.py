"""A stale interpreter must never start the managed services or read configuration."""
import io
from contextlib import redirect_stderr
from unittest.mock import patch
from django.test import SimpleTestCase
from django.core.management.base import CommandError


class RuntimeEntryTests(SimpleTestCase):
    def test_public_entry_rejects_old_python_before_reading_environment_files(self):
        from tools.runtime import backend
        with patch.object(backend.sys, 'argv', ['backend.py', '--check']), patch.object(
                backend.sys, 'version_info', (3, 9, 0)), redirect_stderr(io.StringIO()), patch(
                'dotenv.load_dotenv') as load:
            with self.assertRaises(SystemExit) as caught:
                backend.main()
        self.assertEqual(caught.exception.code, 2)
        load.assert_not_called()

    def test_direct_management_command_cannot_bypass_runtime_gate(self):
        from support_ai.management.commands import run_support_backend as command
        with patch.object(command.sys, 'version_info', (3, 9, 0)), patch.object(command, 'start_service') as start:
            with self.assertRaises(CommandError):
                command.Command().handle(addrport='127.0.0.1:8000', mcp_port=18082, mcp_workers=2)
        start.assert_not_called()
