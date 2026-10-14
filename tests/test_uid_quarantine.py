"""Unprivileged controller-interruption test for durable UID quarantine."""

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

from cep.lifecycle import process_identity
from native import uid_probe
from native.uid_journal import JournalError, Reservation, reserve, reserved_uids
from unittest.mock import patch


class UIDQuarantineTests(unittest.TestCase):
    def test_allocator_skips_stale_durable_reservations(self):
        with (
            patch.object(uid_probe.uid_journal, "reserved_uids", return_value={62017}),
            patch.object(uid_probe.secrets, "randbelow", side_effect=[17, 18]),
            patch.object(uid_probe.pwd, "getpwuid", side_effect=KeyError),
            patch.object(uid_probe.grp, "getgrgid", side_effect=KeyError),
            patch.object(uid_probe, "inventory_uid", return_value=[]),
        ):
            self.assertEqual(uid_probe.choose_uid(), 62018)

    def test_inventory_error_diagnostic_preserves_quarantine(self):
        reservation = Reservation(62017, "a" * 32)
        result = {
            "error_count": 1,
            "inventory_errors": 1,
            "cleaner_status": 0,
            "survivors": 0,
            "worker_status": 0,
            "errors": ["inventory:InventoryError:temporary churn"],
        }
        with patch.object(uid_probe.uid_journal, "release") as release:
            with self.assertRaisesRegex(
                RuntimeError, "inventory:InventoryError:temporary churn"
            ):
                uid_probe.release_verified(62017, reservation, result)
        release.assert_not_called()

    def test_orchestrator_death_after_fork_keeps_uid_reserved(self):
        uid = 62017
        owner = os.getuid()
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix="cep-uid-quarantine-") as temporary:
            journal = Path(temporary)
            journal.chmod(0o700)
            script = r"""
import json, os, sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from native.uid_journal import reserve, reserved_uids
journal, uid, owner = Path(sys.argv[2]), int(sys.argv[3]), int(sys.argv[4])
reservation = reserve(journal, uid, expected_owner_uid=owner)
ready_read, ready_write = os.pipe()
pid = os.fork()
if pid == 0:
    os.close(ready_read)
    os.setsid()
    os.write(ready_write, b"R")
    os.close(ready_write)
    time.sleep(30)
    os._exit(0)
os.close(ready_write)
if os.read(ready_read, 1) != b"R":
    os._exit(4)
os.close(ready_read)
assert reserved_uids(journal, expected_owner_uid=owner) == {uid}
print(json.dumps({"pid": pid, "uid": uid, "nonce": reservation.nonce}), flush=True)
time.sleep(30)
"""
            process = subprocess.Popen(
                [sys.executable, "-I", "-c", script, str(source), str(journal), str(uid), str(owner)],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                text=True,
                start_new_session=True,
            )
            orphan_pid = None
            try:
                ready = process.stdout.readline()
                self.assertTrue(ready, "interrupted controller did not register worker")
                worker = json.loads(ready)
                orphan_pid = worker["pid"]
                self.assertEqual(worker["uid"], uid)
                self.assertIsNotNone(process_identity(orphan_pid))
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=3)
                self.assertEqual(reserved_uids(journal, expected_owner_uid=owner), {uid})
                with self.assertRaises(JournalError):
                    reserve(journal, uid, expected_owner_uid=owner)
                self.assertIsNotNone(process_identity(orphan_pid))
            finally:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=3)
                if orphan_pid is not None:
                    identity = process_identity(orphan_pid)
                    if identity is not None and identity["uid"] == owner:
                        os.kill(orphan_pid, signal.SIGKILL)
                        deadline = time.monotonic() + 3
                        while time.monotonic() < deadline and process_identity(orphan_pid):
                            time.sleep(0.01)
                process.stdout.close()
            self.assertEqual(reserved_uids(journal, expected_owner_uid=owner), {uid})


if __name__ == "__main__":
    unittest.main()
