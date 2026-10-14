"""Logic-only tests; no test here establishes root ownership or cleanup authority."""

from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from native.uid_journal import (
    JournalError,
    Reservation,
    release,
    reserve,
    reserved_uids,
)


class UIDJournalTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.directory.chmod(0o700)
        self.owner = os.getuid()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def evidence(self, reservation: Reservation) -> dict[str, object]:
        return {
            "verified_empty": True,
            "reservation_uid": reservation.uid,
            "reservation_nonce": reservation.nonce,
            "snapshots": [
                {
                    "id": "snapshot-a",
                    "observed_at_ns": 1_000,
                    "stable": True,
                    "processes": [],
                },
                {
                    "id": "snapshot-b",
                    "observed_at_ns": 2_000,
                    "stable": True,
                    "processes": [],
                },
            ],
            "worker_exit_status": 0,
            "expected_worker_status": 0,
            "cleaner_exit_status": 0,
        }

    def test_reservation_is_canonical_and_durable_name_exists(self) -> None:
        reservation = reserve(self.directory, 62001, expected_owner_uid=self.owner)
        path = self.directory / "uid-62001.json"
        payload = path.read_bytes()
        parsed = json.loads(payload)
        self.assertEqual(payload, json.dumps(parsed, sort_keys=True, separators=(",", ":")).encode())
        self.assertEqual(parsed["nonce"], reservation.nonce)
        self.assertEqual(path.stat().st_mode & 0o777, 0o600)
        with self.assertRaises(JournalError):
            reserve(self.directory, 62001, expected_owner_uid=self.owner)

    def test_valid_evidence_releases_matching_record(self) -> None:
        reservation = reserve(self.directory, 62002, expected_owner_uid=self.owner)
        release(
            self.directory,
            reservation,
            self.evidence(reservation),
            expected_owner_uid=self.owner,
        )
        self.assertFalse((self.directory / "uid-62002.json").exists())

    def test_sigkill_worker_status_must_match_expected_status(self) -> None:
        reservation = reserve(self.directory, 62011, expected_owner_uid=self.owner)
        evidence = self.evidence(reservation)
        evidence["worker_exit_status"] = 9
        evidence["expected_worker_status"] = 9
        release(self.directory, reservation, evidence, expected_owner_uid=self.owner)

        reservation = reserve(self.directory, 62012, expected_owner_uid=self.owner)
        evidence = self.evidence(reservation)
        evidence["worker_exit_status"] = 9
        with self.assertRaises(JournalError):
            release(self.directory, reservation, evidence, expected_owner_uid=self.owner)
        self.assertTrue((self.directory / "uid-62012.json").exists())

    def test_reserved_uids_enumerates_and_validates_records(self) -> None:
        reserve(self.directory, 62013, expected_owner_uid=self.owner)
        reserve(self.directory, 62014, expected_owner_uid=self.owner)
        self.assertEqual(
            reserved_uids(self.directory, expected_owner_uid=self.owner),
            {62013, 62014},
        )

    def test_reserved_uids_rejects_malformed_names_records_and_symlinks(self) -> None:
        reserve(self.directory, 62015, expected_owner_uid=self.owner)
        (self.directory / "uid-62016.json").write_text("not-json")
        with self.assertRaises(JournalError):
            reserved_uids(self.directory, expected_owner_uid=self.owner)
        (self.directory / "uid-62016.json").unlink()
        (self.directory / "uid-062017.json").write_text("{}")
        with self.assertRaises(JournalError):
            reserved_uids(self.directory, expected_owner_uid=self.owner)
        (self.directory / "uid-062017.json").unlink()
        (self.directory / "uid-62016.json").symlink_to(self.directory / "uid-62015.json")
        with self.assertRaises(JournalError):
            reserved_uids(self.directory, expected_owner_uid=self.owner)
        with self.assertRaises(JournalError):
            reserve(self.directory, 62018, expected_owner_uid=self.owner)

    def test_fifo_record_is_rejected_without_blocking(self) -> None:
        path = self.directory / "uid-62012.json"
        os.mkfifo(path, 0o600)
        with self.assertRaises(JournalError):
            reserved_uids(self.directory, expected_owner_uid=self.owner)
        self.assertTrue(stat.S_ISFIFO(path.lstat().st_mode))

    def test_invalid_uid_types_and_bounds_are_rejected(self) -> None:
        for uid in (True, 61999, 65000, "62003"):
            with self.subTest(uid=uid), self.assertRaises(JournalError):
                reserve(self.directory, uid, expected_owner_uid=self.owner)  # type: ignore[arg-type]

    def test_directory_mode_and_expected_owner_are_enforced(self) -> None:
        with self.assertRaises(JournalError):
            reserve(self.directory, 62004, expected_owner_uid=self.owner + 1)
        self.directory.chmod(0o755)
        with self.assertRaises(JournalError):
            reserve(self.directory, 62004, expected_owner_uid=self.owner)

    def test_symlink_directory_is_rejected(self) -> None:
        alias = self.directory.parent / f"{self.directory.name}-alias"
        alias.symlink_to(self.directory, target_is_directory=True)
        try:
            with self.assertRaises(JournalError):
                reserve(alias, 62005, expected_owner_uid=self.owner)
        finally:
            alias.unlink()

    def test_existing_malformed_record_always_blocks_reuse(self) -> None:
        (self.directory / "uid-62006.json").write_bytes(b"{}")
        with self.assertRaises(JournalError):
            reserve(self.directory, 62006, expected_owner_uid=self.owner)

    def test_release_rejects_missing_parse_or_permission_evidence(self) -> None:
        reservation = reserve(self.directory, 62007, expected_owner_uid=self.owner)
        bad_evidence = [
            None,
            {},
            {**self.evidence(reservation), "verified_empty": 1},
            {**self.evidence(reservation), "worker_exit_status": False},
            {**self.evidence(reservation), "worker_exit_status": 1},
            {**self.evidence(reservation), "expected_worker_status": 9},
            {**self.evidence(reservation), "cleaner_exit_status": -1},
            {**self.evidence(reservation), "inventory_error": False},
            {**self.evidence(reservation), "reservation_nonce": "0" * 32},
        ]
        for evidence in bad_evidence:
            with self.subTest(evidence=evidence), self.assertRaises(JournalError):
                release(self.directory, reservation, evidence, expected_owner_uid=self.owner)
            self.assertTrue((self.directory / "uid-62007.json").exists())

    def test_release_requires_two_distinct_stable_empty_snapshots(self) -> None:
        reservation = reserve(self.directory, 62008, expected_owner_uid=self.owner)
        base = self.evidence(reservation)
        invalid = [
            [
                {"id": "same", "observed_at_ns": 1, "stable": True, "processes": []}
            ] * 2,
            [
                {"id": "a", "observed_at_ns": 1, "stable": False, "processes": []},
                {"id": "b", "observed_at_ns": 2, "stable": True, "processes": []},
            ],
            [
                {"id": "a", "observed_at_ns": 1, "stable": True, "processes": []},
                {"id": "b", "observed_at_ns": 2, "stable": True, "processes": [{"pid": 7}]},
            ],
            [
                {"id": "a", "observed_at_ns": 1, "stable": True, "processes": []},
                {"id": "b", "observed_at_ns": 2, "stable": True, "processes": [], "error": None},
            ],
            [
                {"id": "a", "observed_at_ns": 2, "stable": True, "processes": []},
                {"id": "b", "observed_at_ns": 1, "stable": True, "processes": []},
            ],
        ]
        for snapshots in invalid:
            with self.subTest(snapshots=snapshots), self.assertRaises(JournalError):
                release(
                    self.directory,
                    reservation,
                    {**base, "snapshots": snapshots},
                    expected_owner_uid=self.owner,
                )
        self.assertTrue((self.directory / "uid-62008.json").exists())

    def test_record_permissions_and_link_count_are_checked(self) -> None:
        reservation = reserve(self.directory, 62009, expected_owner_uid=self.owner)
        path = self.directory / "uid-62009.json"
        path.chmod(0o644)
        with self.assertRaises(JournalError):
            release(
                self.directory,
                reservation,
                self.evidence(reservation),
                expected_owner_uid=self.owner,
            )
        self.assertTrue(path.exists())

    def test_release_is_idempotence_safe_and_nonce_bound(self) -> None:
        reservation = reserve(self.directory, 62010, expected_owner_uid=self.owner)
        evidence = self.evidence(reservation)
        with self.assertRaises(JournalError):
            release(
                self.directory,
                Reservation(reservation.uid, "f" * 32),
                evidence,
                expected_owner_uid=self.owner,
            )
        self.assertTrue((self.directory / "uid-62010.json").exists())
        release(self.directory, reservation, evidence, expected_owner_uid=self.owner)
        with self.assertRaises(JournalError):
            release(self.directory, reservation, evidence, expected_owner_uid=self.owner)


if __name__ == "__main__":
    unittest.main()
