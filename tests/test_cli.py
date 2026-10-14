import contextlib
import io
import json
import unittest
from unittest.mock import patch

from cep.cli import main


class DiagnosticsTests(unittest.TestCase):
    def test_metadata_doctor_needs_no_live_backend(self):
        output = io.StringIO()
        with (
            patch(
                "cep.cli.NativeSandbox", side_effect=ValueError("unavailable")
            ) as backend,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(main(["doctor"]), 0)
        backend.assert_not_called()
        self.assertFalse(json.loads(output.getvalue())["live_qualified"])

    def test_live_qualification_remains_fail_closed(self):
        with (
            patch(
                "cep.cli.NativeSandbox", side_effect=ValueError("unavailable")
            ) as backend,
            contextlib.redirect_stderr(io.StringIO()),
        ):
            self.assertEqual(main(["doctor", "--qualify"]), 2)
        backend.assert_called_once()
