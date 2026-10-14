import concurrent.futures
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from cep.state import Store


class StateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.store = Store(Path(self.temp.name) / "control")

    def job(self, **kwargs):
        return self.store.create_job(
            {"spec_digest": "frozen", "max_attempts": 3, **kwargs}, 10
        )

    def test_explicit_budget_and_contract(self):
        for budget in (0, -1, float("nan"), float("inf"), True):
            with self.assertRaises(ValueError):
                self.store.create_job({"spec_digest": "x"}, budget)
        contract = {"spec_digest": "original"}
        job = self.store.create_job(contract, 10)
        contract["spec_digest"] = "changed"
        self.assertEqual(
            self.store.get_job(job["id"])["contract"]["spec_digest"], "original"
        )
        with self.assertRaises(ValueError):
            self.store.create_job({"repo": self.temp.name}, 10)

    def test_reservation_and_restart(self):
        job = self.job()
        attempt = self.store.start_attempt(job["id"], "implementation")
        other = Store(self.store.control)
        self.assertEqual(other.get_attempt(attempt["id"])["status"], "RUNNING")
        self.assertTrue(Path(attempt["artifact_path"]).is_dir())
        self.assertTrue(other.acquire_lease("integration:repo", job["id"]))
        recovered = other.recover(job["id"])
        self.assertEqual(recovered["status"], "WAITING_INPUT")
        self.assertEqual(other.get_attempt(attempt["id"])["status"], "INTERRUPTED")
        with self.assertRaises(ValueError):
            other.finish_attempt(attempt["id"], "PASSED", {}, 1)
        other.set_status(job["id"], "QUEUED", "requalified")
        resumed = other.start_attempt(job["id"], "implementation")
        self.assertNotEqual(resumed["artifact_path"], attempt["artifact_path"])

    def test_budget_and_attempt_limit(self):
        job = self.job(max_attempts=1)
        attempt = self.store.start_attempt(job["id"], "implementation")
        self.store.finish_attempt(attempt["id"], "FAILED", {"failure": "test"}, 1)
        with self.assertRaises(ValueError):
            self.store.start_attempt(job["id"], "repair")
        self.assertEqual(self.store.get_job(job["id"])["status"], "BLOCKED")
        job = self.job()
        attempt = self.store.start_attempt(job["id"], "implementation")
        self.store.finish_attempt(attempt["id"], "PASSED", {}, 10)
        proof = {
            "mandatory_checks_passed": True,
            "independent_review_passed": True,
            "contract_digest": job["contract_digest"],
        }
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "ACCEPTED", evidence=proof)

    def test_concurrent_resource_ownership(self):
        first, second = self.job(), self.job()

        def acquire(job):
            return self.store.acquire_lease("port:3000", job["id"])

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(acquire, (first, second)))
        self.assertEqual(sum(results), 1)
        owner, loser = (first, second) if results[0] else (second, first)
        with self.assertRaises(ValueError):
            self.store.release_lease("port:3000", loser["id"])
        self.assertFalse(self.store.acquire_lease("port:3000", loser["id"]))
        self.store.release_lease("port:3000", owner["id"])
        self.assertTrue(self.store.acquire_lease("port:3000", loser["id"]))

    def test_concurrent_attempt_reservation(self):
        job = self.job()

        def reserve(_):
            try:
                return self.store.start_attempt(job["id"], "implementation")["id"]
            except ValueError:
                return None

        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            results = list(pool.map(reserve, range(2)))
        self.assertEqual(sum(result is not None for result in results), 1)

    def test_no_unproven_completion(self):
        job = self.job()
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "ACCEPTED")
        proof = {
            "mandatory_checks_passed": True,
            "independent_review_passed": True,
            "contract_digest": "stale",
        }
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "ACCEPTED", evidence=proof)
        attempt = self.store.start_attempt(job["id"], "final_review")
        self.store.finish_attempt(attempt["id"], "PASSED", {}, 1)
        proof["contract_digest"] = job["contract_digest"]
        self.store.set_status(job["id"], "ACCEPTED", evidence=proof)
        self.assertEqual(self.store.get_job(job["id"])["status"], "ACCEPTED")
        self.assertTrue(self.store.acquire_lease("integration:repo:main", job["id"]))
        with self.assertRaises(ValueError):
            self.store.acquire_lease("port:3000", job["id"])

    def test_future_schema_rejected(self):
        with closing(sqlite3.connect(self.store.path)) as db:
            db.execute("PRAGMA user_version=999")
            db.commit()
        with self.assertRaises(ValueError):
            Store(self.store.control)

    def test_repeated_crash_resume_cannot_reset_active_budget(self):
        job = self.job(max_attempts=10)
        with patch("cep.state._boot_id", return_value="boot-a"):
            with patch("cep.state.time.monotonic", return_value=100):
                self.store.start_attempt(job["id"], "implement")
            with patch("cep.state.time.monotonic", return_value=103):
                recovered = self.store.recover(job["id"])
            self.assertEqual(recovered["charged_seconds"], 3)
            self.assertEqual(self.store.recover(job["id"])["charged_seconds"], 3)
            self.store.set_status(job["id"], "QUEUED", "explicit resume")
            with patch("cep.state.time.monotonic", return_value=104):
                self.store.start_attempt(job["id"], "implement")
            with patch("cep.state.time.monotonic", return_value=108):
                recovered = self.store.recover(job["id"])
            self.assertEqual(recovered["charged_seconds"], 7)
            self.store.set_status(job["id"], "QUEUED", "explicit resume")
            with patch("cep.state.time.monotonic", return_value=109):
                self.store.start_attempt(job["id"], "implement")
            with patch("cep.state.time.monotonic", return_value=120):
                recovered = self.store.recover(job["id"])
        self.assertEqual(recovered["charged_seconds"], 10)
        self.assertEqual(recovered["status"], "BLOCKED")
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "QUEUED", "cannot reset")

    def test_cross_boot_recovery_charges_execution_bound(self):
        job = self.job()
        with (
            patch("cep.state._boot_id", return_value="boot-a"),
            patch("cep.state.time.monotonic", return_value=100),
        ):
            attempt = self.store.start_attempt(job["id"], "implement", max_seconds=2)
        with (
            patch("cep.state._boot_id", return_value="boot-b"),
            patch("cep.state.time.monotonic", return_value=1),
        ):
            recovered = self.store.recover(job["id"])
        self.assertEqual(recovered["charged_seconds"], 2)
        self.assertEqual(recovered["remaining_seconds"], 8)
        self.assertEqual(self.store.get_attempt(attempt["id"])["elapsed_seconds"], 2)
        self.assertIn(
            "conservatively",
            self.store.get_attempt(attempt["id"])["evidence"]["budget_accounting"],
        )

    def test_interrupted_gate_is_charged_without_running_attempt(self):
        job = self.job()
        with (
            patch("cep.state._boot_id", return_value="boot-a"),
            patch("cep.state.time.monotonic", return_value=100),
        ):
            reservation = self.store.reserve_time(job["id"], "gate:tests", 4)
        with (
            patch("cep.state._boot_id", return_value="boot-a"),
            patch("cep.state.time.monotonic", return_value=130),
        ):
            recovered = self.store.recover(job["id"])
        self.assertEqual(recovered["charged_seconds"], 4)
        self.assertEqual(self.store.recover(job["id"])["charged_seconds"], 4)
        with self.assertRaises(ValueError):
            self.store.finish_time(reservation["reservation_id"], 1)

    def test_external_reservation_is_exclusive_and_blocks_acceptance(self):
        job = self.job()
        reservation = self.store.reserve_time(job["id"], "qualification", 100)
        self.assertEqual(reservation["max_seconds"], 10)
        with self.assertRaises(ValueError):
            self.store.reserve_time(job["id"], "gate", 1)
        with self.assertRaises(ValueError):
            self.store.start_attempt(job["id"], "implement")
        proof = {
            "mandatory_checks_passed": True,
            "independent_review_passed": True,
            "contract_digest": job["contract_digest"],
        }
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "ACCEPTED", evidence=proof)
        self.store.finish_time(reservation["reservation_id"], 2)
        self.assertEqual(self.store.get_job(job["id"])["charged_seconds"], 2)
        with self.assertRaises(ValueError):
            self.store.finish_time(reservation["reservation_id"], 2)

    def test_cancellation_remains_terminal_during_budget_settlement(self):
        job = self.job()
        attempt = self.store.start_attempt(job["id"], "implement")
        self.store.set_status(job["id"], "CANCELLED", "operator cancellation")
        self.store.finish_attempt(attempt["id"], "FAILED", {}, 10)
        self.store.charge_seconds(job["id"], 2)
        self.assertEqual(self.store.get_job(job["id"])["status"], "CANCELLED")
        self.assertEqual(self.store.recover(job["id"])["status"], "CANCELLED")
        with self.assertRaises(ValueError):
            self.store.set_status(job["id"], "QUEUED")
        job = self.job()
        reservation = self.store.reserve_time(job["id"], "gate", 10)
        self.store.set_status(job["id"], "CANCELLED")
        self.store.finish_time(reservation["reservation_id"], 10)
        self.assertEqual(self.store.get_job(job["id"])["status"], "CANCELLED")

    def test_legacy_interrupted_attempt_conservatively_consumes_budget(self):
        job = self.job()
        attempt = self.store.start_attempt(job["id"], "implement")
        with self.store._connect() as db:
            db.execute(
                "UPDATE events SET payload=? WHERE job_id=? AND kind='ATTEMPT_RESERVED'",
                (
                    json.dumps({"attempt_id": attempt["id"], "phase": "implement"}),
                    job["id"],
                ),
            )
        recovered = self.store.recover(job["id"])
        self.assertEqual(recovered["status"], "BLOCKED")
        self.assertEqual(recovered["remaining_seconds"], 0)

    def test_cancelled_interruption_is_accounted_without_resuming(self):
        job = self.job()
        with patch("cep.state._boot_id", return_value="boot-a"):
            with patch("cep.state.time.monotonic", return_value=100):
                attempt = self.store.start_attempt(
                    job["id"], "implement", max_seconds=5
                )
            self.store.set_status(job["id"], "CANCELLED")
            with patch("cep.state.time.monotonic", return_value=103):
                recovered = self.store.recover(job["id"])
        self.assertEqual(recovered["status"], "CANCELLED")
        self.assertEqual(recovered["charged_seconds"], 3)
        self.assertEqual(self.store.get_attempt(attempt["id"])["status"], "INTERRUPTED")
        with self.assertRaises(ValueError):
            self.store.start_attempt(job["id"], "implement")
