import math
import os
from pathlib import Path
import sys
import signal
import tempfile
import time
import unittest

from cep.process import clean_env, run_process


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def run_python(self, script, timeout=3, **kwargs):
        return run_process(
            [sys.executable, "-I", "-c", script],
            self.root,
            timeout,
            env=clean_env(self.root / "scratch"),
            **kwargs,
        )

    def test_nonfinite_and_nonpositive_timeouts_rejected(self):
        for timeout in (math.nan, math.inf, -math.inf, 0, -1, True):
            with self.subTest(timeout=timeout):
                with self.assertRaises(ValueError):
                    self.run_python("pass", timeout)

    def test_output_limit_is_bounded_failure(self):
        result = self.run_python(
            "import os;\nwhile True: os.write(1,b'x'*65536)", output_limit=100000
        )
        self.assertTrue(result["output_exceeded"])
        self.assertLessEqual(len(result["stdout"]), 200000)
        self.assertLess(result["elapsed_seconds"], 3)

    def test_timeout_drains_finitely(self):
        started = time.monotonic()
        result = self.run_python(
            "import time; print('before',flush=True); time.sleep(20)", 0.1
        )
        self.assertTrue(result["timed_out"])
        self.assertIn("before", result["stdout"])
        self.assertLess(time.monotonic() - started, 3)

    def test_detached_inherited_pipe_cannot_block_drain(self):
        # Deliberately does not certify descendant containment: cleanup below is
        # performed by this trusted fixture, not by run_process.
        child = None
        try:
            result = self.run_python(
                "import subprocess,sys; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(20)'],start_new_session=True); "
                "print(p.pid,flush=True)",
                3,
            )
            child = int(result["stdout"].strip())
            self.assertLess(result["elapsed_seconds"], 1)
        finally:
            if child is not None:
                try:
                    os.kill(child, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def test_redacts_output_and_recorded_arguments(self):
        token = "ghp_" + "fixtureToken123"
        result = self.run_python(f"print('{token}')", record_argv=["python", token])
        self.assertNotIn(token, result["stdout"])
        self.assertNotIn(token, repr(result["argv"]))
