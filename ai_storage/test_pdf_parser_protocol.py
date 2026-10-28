"""Regression for real-PDF helper banners corrupting the worker JSON channel."""
from contextlib import redirect_stdout
import io
import json
import unittest
from unittest.mock import patch

from ai_storage.pdf_pipeline import parser


class PdfParserProtocolTests(unittest.TestCase):
    def invoke(self, effect, output=None):
        output = output if output is not None else io.StringIO()
        with patch.object(parser, 'parse', side_effect=effect), patch.object(parser.sys, 'platform', 'win32'), \
                patch.object(parser.sys, 'argv', ['parser', 'source.pdf', '1', 'preview.png', '{}']), redirect_stdout(output):
            parser.main()
        return output.getvalue()

    def test_library_banner_cannot_corrupt_json(self):
        def noisy(*args):
            print('Third-party PDF helper banner')
            return {'number': 1, 'blocks': [{'text': 'OCR paragraph'}]}
        value = self.invoke(noisy)
        self.assertEqual(json.loads(value)['number'], 1)
        self.assertNotIn('banner', value)

    def test_failed_parse_does_not_emit_partial_json_or_content(self):
        def broken(*args):
            print('Untrusted PDF diagnostics')
            raise ValueError('parse failed')
        output = io.StringIO()
        with self.assertRaises(ValueError):
            self.invoke(broken, output)
        self.assertEqual(output.getvalue(), '')
