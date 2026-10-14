"""Real disposable-process watchdog tests; no external resources or credentials."""

import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from cep.lifecycle import (
    cleanup_registry,
    finish,
    guarded_popen,
    process_identity,
    supervise,
)


class LifecycleTests(unittest.TestCase):
    def test_cleanup_missing_registry_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(cleanup_registry(Path(directory) / "not-created"), [])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.registry = self.root / "registry"
        self.processes = []
        self.addCleanup(self.cleanup)

    def cleanup(self):
        if self.registry.exists() and not self.registry.is_symlink():
            cleanup_registry(self.registry)
        for process in self.processes:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=2)

    def child(self):
        process = subprocess.Popen(
            [sys.executable, "-I", "-c", "import time; time.sleep(20)"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        self.processes.append(process)
        return process

    def test_deadline_terminates_owned_detached_group(self):
        child = self.child()
        record = supervise(child.pid, self.registry, 0.3)
        child.wait(timeout=3)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            stored = json.loads(Path(record["path"]).read_text())
            if stored["status"] == "DEADLINE_KILLED":
                break
            time.sleep(0.02)
        self.assertEqual(stored["status"], "DEADLINE_KILLED")
        finish(record)

    def test_finish_only_stops_watchdog_not_command(self):
        child = self.child()
        record = supervise(child.pid, self.registry, 0.5)
        finish(record)
        time.sleep(0.6)
        self.assertIsNone(child.poll())
        self.assertEqual(
            json.loads(Path(record["path"]).read_text())["status"], "FINISHED"
        )

    def test_birth_identity_mismatch_never_kills_target(self):
        child = self.child()
        record = supervise(child.pid, self.registry, 10)
        finish(record)
        changed = json.loads(Path(record["path"]).read_text())
        changed["target"]["birth"][0] += 1
        changed["status"] = "RUNNING"
        Path(record["path"]).write_text(json.dumps(changed))
        result = cleanup_registry(self.registry)
        self.assertFalse(result[0]["target_killed"])
        self.assertIsNone(child.poll())

    def test_cleanup_kills_matching_registered_commands(self):
        child = self.child()
        record = supervise(child.pid, self.registry, 10)
        result = cleanup_registry(self.registry)
        self.assertTrue(result[0]["target_killed"])
        child.wait(timeout=2)
        self.assertEqual(child.returncode, -signal.SIGKILL)
        self.assertEqual(
            json.loads(Path(record["path"]).read_text())["status"], "CLEANED"
        )

    def test_watchdog_survives_launcher_killed(self):
        source = Path(__file__).resolve().parents[1] / "src"
        script = (
            "import sys,subprocess,json,time; from pathlib import Path; "
            f"sys.path.insert(0,{str(source)!r}); "
            "from cep.lifecycle import supervise; "
            "p=subprocess.Popen([sys.executable,'-I','-c','import time;time.sleep(20)'],start_new_session=True); "
            f"r=supervise(p.pid,Path({str(self.registry)!r}),.5); "
            "print(json.dumps(r),flush=True);time.sleep(20)"
        )
        launcher = subprocess.Popen(
            [sys.executable, "-I", "-c", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        self.processes.append(launcher)
        try:
            record = json.loads(launcher.stdout.readline())
            os.killpg(launcher.pid, signal.SIGKILL)
            launcher.wait(timeout=2)
            deadline = time.monotonic() + 3
            while (
                time.monotonic() < deadline
                and process_identity(record["target"]["pid"]) is not None
            ):
                time.sleep(0.05)
            self.assertIsNone(process_identity(record["target"]["pid"]))
        finally:
            launcher.stdout.close()

    def test_invalid_budget_and_registry_symlinks_rejected(self):
        child = self.child()
        for timeout in (0, -1, math.nan, math.inf, True):
            with self.assertRaises(ValueError):
                supervise(child.pid, self.registry, timeout)
        real = self.root / "real"
        real.mkdir(mode=0o700)
        self.registry.symlink_to(real, target_is_directory=True)
        with self.assertRaises(ValueError):
            supervise(child.pid, self.registry, 1)

    def test_symlink_record_never_read_or_overwritten(self):
        child = self.child()
        record = supervise(child.pid, self.registry, 10)
        finish(record)
        secret = self.root / "secret"
        secret.write_text("private")
        Path(record["path"]).unlink()
        Path(record["path"]).symlink_to(secret)
        results = cleanup_registry(self.registry)
        self.assertIn("error", results[0])
        self.assertEqual(secret.read_text(), "private")

    def test_guarded_exec_has_real_streams_and_durable_registration(self):
        process = guarded_popen(
            [
                sys.executable,
                "-I",
                "-c",
                "import sys;print('out');print('err',file=sys.stderr)",
            ],
            self.root,
            {"PATH": os.defpath},
            self.registry,
            3,
        )
        try:
            self.assertTrue(Path(process.registration["path"]).exists())
            self.assertEqual(process.wait(timeout=2), 0)
            self.assertEqual(process.stdout.read(), b"out\n")
            self.assertEqual(process.stderr.read(), b"err\n")
            self.assertEqual(process.poll(), 0)
        finally:
            process.stdout.close()
            process.stderr.close()
            finish(process.registration)

    def test_guarded_worker_cannot_execute_if_launcher_dies_before_registration(self):
        source = Path(__file__).resolve().parents[1] / "src"
        marker = self.root / "untrusted-executed"
        target_script = (
            f"from pathlib import Path;Path({str(marker)!r}).write_text('unsafe')"
        )
        script = (
            "import sys,time,os,json;from pathlib import Path;"
            f"sys.path.insert(0,{str(source)!r});"
            "from cep.lifecycle import guarded_popen;"
            "\ndef milestone(pid):\n print(pid,flush=True);time.sleep(20)\n"
            f"guarded_popen([sys.executable,'-I','-c',{target_script!r}],Path({str(self.root)!r}),"
            f"{{'PATH':os.defpath}},Path({str(self.registry)!r}),3,before_release=milestone)"
        )
        launcher = subprocess.Popen(
            [sys.executable, "-I", "-c", script],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            start_new_session=True,
        )
        self.processes.append(launcher)
        try:
            held_pid = int(launcher.stdout.readline())
            os.killpg(launcher.pid, signal.SIGKILL)
            launcher.wait(timeout=2)
            deadline = time.monotonic() + 3
            while (
                time.monotonic() < deadline and process_identity(held_pid) is not None
            ):
                time.sleep(0.02)
            self.assertIsNone(process_identity(held_pid))
            self.assertFalse(marker.exists())
            self.assertEqual(list(self.registry.glob("*.json")), [])
        finally:
            launcher.stdout.close()

    def test_guarded_registration_error_never_executes_worker(self):
        marker = self.root / "executed"

        def reject(_):
            raise RuntimeError("injected registration interruption")

        with self.assertRaises(RuntimeError):
            guarded_popen(
                [
                    sys.executable,
                    "-I",
                    "-c",
                    f"from pathlib import Path;Path({str(marker)!r}).write_text('unsafe')",
                ],
                self.root,
                {"PATH": os.defpath},
                self.registry,
                3,
                before_release=reject,
            )
        self.assertFalse(marker.exists())
