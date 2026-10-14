import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.security_gate import main


class SecurityGateTests(unittest.TestCase):
    def check(self, findings, errors=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report, baseline = root / "report.json", root / "baseline.json"
            report.write_text(json.dumps({"results": findings, "errors": errors or []}))
            baseline.write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "findings": [
                            {
                                "file": "process.py",
                                "test_id": "B603",
                                "severity": "LOW",
                                "count": 1,
                            }
                        ],
                    }
                )
            )
            with (
                patch("sys.argv", ["gate", str(report), "--baseline", str(baseline)]),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                main()

    def finding(self, severity="LOW", code="B603"):
        return {
            "filename": "src/cep/process.py",
            "test_id": code,
            "issue_severity": severity,
        }

    def test_reviewed_low_retained(self):
        self.check([self.finding()])

    def test_material_or_new_low_rejected(self):
        for finding in (self.finding("HIGH"), self.finding(code="B999")):
            with self.assertRaises(ValueError):
                self.check([finding])

    def test_extra_findings_and_scanner_errors_rejected(self):
        with self.assertRaises(ValueError):
            self.check([self.finding(), self.finding()])
        with self.assertRaises(ValueError):
            self.check([], ["scanner failed"])
