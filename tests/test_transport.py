"""Transport result validation, without a live Codex completion claim."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cep.transport import CodexTransport


class FakeSandbox:
    codex = "/fake/codex"

    def permissions(self, repo, scratch, **kwargs):
        return {}

    def override(self, profile):
        return "permissions.cep={}"


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.transport = CodexTransport(FakeSandbox())

    def invoke(self, flag=None):
        artifact = self.root / (flag or "normal")

        def complete_result(argv, cwd, timeout, **kwargs):
            # Even a valid structured PASS and zero exit cannot override limits.
            output = Path(argv[argv.index("--output-last-message") + 1])
            output.write_text(
                json.dumps(
                    {
                        "phase": "review",
                        "verdict": "PASS",
                        "summary": "complete",
                        "blocking_findings": [],
                        "questions": [],
                    }
                )
            )
            result = {
                "argv": ["fake-codex"],
                "exit_code": 0,
                "timed_out": False,
                "output_exceeded": False,
                "stdout": "",
                "stderr": "",
                "elapsed_seconds": 0.001,
            }
            if flag:
                result[flag] = True
            return result

        with patch("cep.transport.run_process", side_effect=complete_result):
            return self.transport.invoke(self.repo, artifact, "review", "inspect", 1)

    def test_zero_exit_complete_response_rejected_after_output_limit(self):
        with self.assertRaises(RuntimeError):
            self.invoke("output_exceeded")
        recorded = json.loads((self.root / "output_exceeded/process.json").read_text())
        self.assertEqual(recorded["exit_code"], 0)
        self.assertTrue(recorded["output_exceeded"])
        self.assertTrue((self.root / "output_exceeded/result.json").exists())

    def test_zero_exit_complete_response_rejected_after_timeout(self):
        with self.assertRaises(RuntimeError):
            self.invoke("timed_out")
        self.assertTrue(
            json.loads((self.root / "timed_out/process.json").read_text())["timed_out"]
        )

    def test_unflagged_complete_response_is_structurally_valid(self):
        result = self.invoke()
        self.assertEqual(result["verdict"], "PASS")
        self.assertTrue(result["independent"])
