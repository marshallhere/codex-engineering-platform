"""Transactional controller state. Workers must never receive this directory."""

from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import math
import ctypes
import platform
from pathlib import Path
import sqlite3
import time
import uuid

SCHEMA_VERSION = 1
STATUSES = {"QUEUED", "RUNNING", "WAITING_INPUT", "ACCEPTED", "BLOCKED", "CANCELLED"}


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _seconds(value, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
    ):
        raise ValueError("seconds must be a finite number")
    if value < 0 or (positive and value <= 0):
        raise ValueError(
            "seconds must be positive" if positive else "seconds cannot be negative"
        )
    return float(value)


def _boot_id():
    """Stable boot identity; unavailable identity triggers conservative recovery."""
    if platform.system() == "Linux":
        try:
            return Path("/proc/sys/kernel/random/boot_id").read_text().strip() or None
        except OSError:
            return None
    if platform.system() == "Darwin":
        query = ctypes.CDLL(None, use_errno=True).sysctlbyname
        query.argtypes = [
            ctypes.c_char_p,
            ctypes.c_void_p,
            ctypes.POINTER(ctypes.c_size_t),
            ctypes.c_void_p,
            ctypes.c_size_t,
        ]
        query.restype = ctypes.c_int
        size = ctypes.c_size_t(0)
        if (
            query(b"kern.bootsessionuuid", None, ctypes.byref(size), None, 0)
            or not 0 < size.value <= 128
        ):
            return None
        buffer = ctypes.create_string_buffer(size.value)
        if query(b"kern.bootsessionuuid", buffer, ctypes.byref(size), None, 0):
            return None
        return buffer.value.decode("ascii", errors="strict") or None
    return None


def _reservation(seconds):
    return {
        "max_seconds": seconds,
        "started_monotonic": time.monotonic(),
        "boot_id": _boot_id(),
    }


def _recovered_seconds(timing, remaining):
    if not isinstance(timing, dict):
        return remaining, "legacy reservation lacks active-time identity"
    bound = timing.get("max_seconds")
    if (
        isinstance(bound, bool)
        or not isinstance(bound, (int, float))
        or not math.isfinite(bound)
        or bound <= 0
    ):
        return remaining, "reservation lacks a valid execution bound"
    bound = min(float(bound), remaining)
    started = timing.get("started_monotonic")
    current = time.monotonic()
    if (
        timing.get("boot_id") is not None
        and timing["boot_id"] == _boot_id()
        and isinstance(started, (int, float))
        and not isinstance(started, bool)
        and math.isfinite(started)
        and 0 <= started <= current
    ):
        return min(bound, current - started), "same-boot active-clock upper bound"
    return bound, "unknown active clock; execution reservation conservatively charged"


class Store:
    def __init__(self, control: Path):
        self.control = Path(control).expanduser().resolve()
        self.control.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.control / "state.sqlite3"
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(f"unsupported state schema {version}")
            if version == 0:
                existing = db.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
                if existing:
                    raise ValueError("unversioned existing database")
                schema = """
                    CREATE TABLE jobs (
                      id TEXT PRIMARY KEY, contract TEXT NOT NULL, contract_digest TEXT NOT NULL,
                      budget_seconds REAL NOT NULL, charged_seconds REAL NOT NULL DEFAULT 0,
                      status TEXT NOT NULL, created REAL NOT NULL, updated REAL NOT NULL);
                    CREATE TABLE attempts (
                      id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), phase TEXT NOT NULL,
                      status TEXT NOT NULL, artifact_path TEXT NOT NULL UNIQUE, evidence TEXT,
                      started REAL NOT NULL, finished REAL, elapsed_seconds REAL NOT NULL DEFAULT 0);
                    CREATE TABLE events (
                      id INTEGER PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id),
                      kind TEXT NOT NULL, payload TEXT NOT NULL, created REAL NOT NULL);
                    CREATE TABLE leases (
                      resource TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id), created REAL NOT NULL);
                    PRAGMA user_version=1;
                """
                for statement in schema.split(";"):
                    if statement.strip():
                        db.execute(statement)
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _job(row):
        if row is None:
            raise KeyError("unknown job")
        result = dict(row)
        result["contract"] = json.loads(result["contract"])
        result["remaining_seconds"] = max(
            0.0, result["budget_seconds"] - result["charged_seconds"]
        )
        return result

    @staticmethod
    def _event(db, job_id, kind, payload):
        db.execute(
            "INSERT INTO events(job_id,kind,payload,created) VALUES(?,?,?,?)",
            (job_id, kind, _json(payload), time.time()),
        )

    def create_job(self, contract: dict, budget_seconds: float) -> dict:
        budget = _seconds(budget_seconds, positive=True)
        if not isinstance(contract, dict) or not contract:
            raise ValueError("a frozen contract is required")
        from .specs import validate_task_graph

        if "tasks" in contract:
            validate_task_graph(contract["tasks"])
        limit = contract.get("max_attempts", 12)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
            raise ValueError("max_attempts must be a positive integer")
        # Recognize the portable manifest shapes without embedding stack knowledge.
        roots = []
        for key in ("repo", "project", "project_root", "repo_root"):
            value = contract.get(key)
            if isinstance(value, str):
                roots.append(value)
        for repo in contract.get("repositories", []):
            if isinstance(repo, dict) and isinstance(repo.get("path"), str):
                roots.append(repo["path"])
        for root in roots:
            if self.control.is_relative_to(Path(root).expanduser().resolve()):
                raise ValueError("control directory must be outside project roots")
        frozen = _json(contract)
        job_id = str(uuid.uuid4())
        now = time.time()
        with self._connect() as db:
            db.execute(
                "INSERT INTO jobs(id,contract,contract_digest,budget_seconds,status,created,updated) VALUES(?,?,?,?,?,?,?)",
                (
                    job_id,
                    frozen,
                    hashlib.sha256(frozen.encode()).hexdigest(),
                    budget,
                    "QUEUED",
                    now,
                    now,
                ),
            )
            self._event(db, job_id, "CREATED", {"budget_seconds": budget})
        return self.get_job(job_id)

    def get_job(self, job_id: str) -> dict:
        with self._connect() as db:
            return self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )

    def list_jobs(self) -> list[dict]:
        with self._connect() as db:
            return [
                self._job(row)
                for row in db.execute("SELECT * FROM jobs ORDER BY created,id")
            ]

    def event(self, job_id: str, kind: str, payload: dict | None = None):
        with self._connect() as db:
            self._event(db, job_id, kind, payload or {})

    def events(self, job_id: str) -> list[dict]:
        with self._connect() as db:
            return [
                {**dict(row), "payload": json.loads(row["payload"])}
                for row in db.execute(
                    "SELECT * FROM events WHERE job_id=? ORDER BY id", (job_id,)
                )
            ]

    @staticmethod
    def _pending_time(db, job_id):
        reservations = {}
        for row in db.execute(
            "SELECT kind,payload FROM events WHERE job_id=? AND kind IN ('TIME_RESERVED','TIME_FINISHED') ORDER BY id",
            (job_id,),
        ):
            payload = json.loads(row["payload"])
            if row["kind"] == "TIME_RESERVED":
                reservations[payload["reservation_id"]] = payload
            else:
                reservations.pop(payload["reservation_id"], None)
        return reservations

    def reserve_time(self, job_id: str, label: str, max_seconds: float) -> dict:
        """Durably reserve external execution (gates/qualification) before launch."""
        bound = _seconds(max_seconds, positive=True)
        if not isinstance(label, str) or not label.strip():
            raise ValueError("execution reservation label is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )
            if (
                job["status"] in {"ACCEPTED", "CANCELLED", "BLOCKED", "WAITING_INPUT"}
                or job["remaining_seconds"] <= 0
            ):
                raise ValueError(
                    "inactive or exhausted job cannot reserve execution time"
                )
            if (
                self._pending_time(db, job_id)
                or db.execute(
                    "SELECT 1 FROM attempts WHERE job_id=? AND status='RUNNING'",
                    (job_id,),
                ).fetchone()
            ):
                raise ValueError("job already has outstanding execution time")
            timing = _reservation(min(bound, job["remaining_seconds"]))
            record = {
                "reservation_id": str(uuid.uuid4()),
                "job_id": job_id,
                "label": label,
                **timing,
            }
            self._event(db, job_id, "TIME_RESERVED", record)
        return record

    def finish_time(self, reservation_id: str, elapsed_seconds: float):
        elapsed = _seconds(elapsed_seconds)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT job_id,payload FROM events WHERE kind='TIME_RESERVED' AND json_extract(payload,'$.reservation_id')=?",
                (reservation_id,),
            ).fetchone()
            if row is None:
                raise KeyError("unknown time reservation")
            if reservation_id not in self._pending_time(db, row["job_id"]):
                raise ValueError("time reservation already finished")
            now = time.time()
            db.execute(
                "UPDATE jobs SET charged_seconds=charged_seconds+?,updated=? WHERE id=?",
                (elapsed, now, row["job_id"]),
            )
            db.execute(
                "UPDATE jobs SET status='BLOCKED' WHERE id=? AND charged_seconds>=budget_seconds AND status!='CANCELLED'",
                (row["job_id"],),
            )
            self._event(
                db,
                row["job_id"],
                "TIME_FINISHED",
                {
                    "reservation_id": reservation_id,
                    "elapsed_seconds": elapsed,
                    "interrupted": False,
                },
            )

    def start_attempt(
        self, job_id: str, phase: str, *, max_seconds: float | None = None
    ) -> dict:
        if not isinstance(phase, str) or not phase.strip():
            raise ValueError("attempt phase is required")
        failure = None
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )
            if job["status"] in {"ACCEPTED", "CANCELLED", "BLOCKED", "WAITING_INPUT"}:
                raise ValueError(f"job is {job['status']}")
            if self._pending_time(db, job_id):
                raise ValueError("job has outstanding external execution time")
            if db.execute(
                "SELECT 1 FROM attempts WHERE job_id=? AND status='RUNNING'", (job_id,)
            ).fetchone():
                raise ValueError("job already has a running attempt")
            count = db.execute(
                "SELECT count(*) FROM attempts WHERE job_id=?", (job_id,)
            ).fetchone()[0]
            if job["remaining_seconds"] <= 0 or count >= job["contract"].get(
                "max_attempts", 12
            ):
                failure = (
                    "active-time budget exhausted"
                    if job["remaining_seconds"] <= 0
                    else "attempt limit exhausted"
                )
                db.execute(
                    "UPDATE jobs SET status='BLOCKED',updated=? WHERE id=?",
                    (time.time(), job_id),
                )
                self._event(db, job_id, "BLOCKED", {"reason": failure})
            else:
                attempt_id = str(uuid.uuid4())
                artifact = str(self.control / "attempts" / attempt_id)
                now = time.time()
                db.execute(
                    "INSERT INTO attempts(id,job_id,phase,status,artifact_path,started) VALUES(?,?,?,?,?,?)",
                    (attempt_id, job_id, phase, "RUNNING", artifact, now),
                )
                db.execute(
                    "UPDATE jobs SET status='RUNNING',updated=? WHERE id=?",
                    (now, job_id),
                )
                self._event(
                    db,
                    job_id,
                    "ATTEMPT_RESERVED",
                    {
                        "attempt_id": attempt_id,
                        "phase": phase,
                        **_reservation(
                            min(
                                job["remaining_seconds"],
                                _seconds(max_seconds, positive=True)
                                if max_seconds is not None
                                else job["remaining_seconds"],
                            )
                        ),
                    },
                )
        if failure:
            raise ValueError(failure)
        # Reservation is durable before any artifact or subprocess is created.
        Path(artifact).mkdir(parents=True, mode=0o700)
        return self.get_attempt(attempt_id)

    def get_attempt(self, attempt_id: str) -> dict:
        with self._connect() as db:
            row = db.execute(
                "SELECT * FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown attempt")
            result = dict(row)
            result["evidence"] = (
                json.loads(result["evidence"]) if result["evidence"] else None
            )
            return result

    def attempts(self, job_id: str) -> list[dict]:
        with self._connect() as db:
            ids = [
                row[0]
                for row in db.execute(
                    "SELECT id FROM attempts WHERE job_id=? ORDER BY started,id",
                    (job_id,),
                )
            ]
        return [self.get_attempt(attempt_id) for attempt_id in ids]

    def finish_attempt(
        self, attempt_id: str, status: str, evidence: dict, elapsed_seconds: float
    ):
        if status not in {"PASSED", "FAILED", "INTERRUPTED"}:
            raise ValueError("invalid attempt status")
        elapsed = _seconds(elapsed_seconds)
        frozen = _json(evidence)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT * FROM attempts WHERE id=?", (attempt_id,)
            ).fetchone()
            if row is None:
                raise KeyError("unknown attempt")
            if row["status"] != "RUNNING":
                raise ValueError("attempt already finished")
            now = time.time()
            db.execute(
                "UPDATE attempts SET status=?,evidence=?,elapsed_seconds=?,finished=? WHERE id=?",
                (status, frozen, elapsed, now, attempt_id),
            )
            db.execute(
                "UPDATE jobs SET charged_seconds=charged_seconds+?,updated=? WHERE id=?",
                (elapsed, now, row["job_id"]),
            )
            db.execute(
                "UPDATE jobs SET status='BLOCKED' WHERE id=? AND charged_seconds>=budget_seconds AND status!='CANCELLED'",
                (row["job_id"],),
            )
            self._event(
                db,
                row["job_id"],
                "ATTEMPT_FINISHED",
                {
                    "attempt_id": attempt_id,
                    "status": status,
                    "elapsed_seconds": elapsed,
                },
            )

    def charge_seconds(self, job_id: str, seconds: float):
        elapsed = _seconds(seconds)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            self._job(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())
            db.execute(
                "UPDATE jobs SET charged_seconds=charged_seconds+?,updated=? WHERE id=?",
                (elapsed, time.time(), job_id),
            )
            db.execute(
                "UPDATE jobs SET status='BLOCKED' WHERE id=? AND charged_seconds>=budget_seconds AND status!='CANCELLED'",
                (job_id,),
            )
            self._event(db, job_id, "TIME_CHARGED", {"seconds": elapsed})

    def set_status(
        self, job_id: str, status: str, reason: str = "", evidence: dict | None = None
    ):
        if status not in STATUSES:
            raise ValueError("invalid job status")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )
            if job["status"] == "CANCELLED" and status != "CANCELLED":
                raise ValueError("cancelled jobs cannot resume")
            if (
                status in {"QUEUED", "RUNNING", "WAITING_INPUT"}
                and job["remaining_seconds"] <= 0
            ):
                raise ValueError("exhausted jobs cannot resume")
            if status == "ACCEPTED":
                proof = evidence or {}
                if job["remaining_seconds"] <= 0:
                    raise ValueError("exhausted jobs cannot be accepted")
                if db.execute(
                    "SELECT 1 FROM attempts WHERE job_id=? AND status='RUNNING'",
                    (job_id,),
                ).fetchone():
                    raise ValueError("running attempts cannot be accepted")
                if self._pending_time(db, job_id):
                    raise ValueError(
                        "outstanding external execution cannot be accepted"
                    )
                if (
                    proof.get("mandatory_checks_passed") is not True
                    or proof.get("independent_review_passed") is not True
                    or proof.get("contract_digest") != job["contract_digest"]
                ):
                    raise ValueError("candidate-bound completion proof required")
            db.execute(
                "UPDATE jobs SET status=?,updated=? WHERE id=?",
                (status, time.time(), job_id),
            )
            self._event(db, job_id, status, {"reason": reason, "evidence": evidence})

    def acquire_lease(self, resource: str, job_id: str) -> bool:
        if not isinstance(resource, str) or not resource.strip():
            raise ValueError("resource is required")
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )
            if job["status"] in {"CANCELLED", "BLOCKED"} or (
                job["status"] == "ACCEPTED" and not resource.startswith("integration:")
            ):
                raise ValueError("inactive job cannot acquire resources")
            owner = db.execute(
                "SELECT job_id FROM leases WHERE resource=?", (resource,)
            ).fetchone()
            if owner:
                return owner[0] == job_id
            db.execute(
                "INSERT INTO leases VALUES(?,?,?)", (resource, job_id, time.time())
            )
            self._event(db, job_id, "LEASE_ACQUIRED", {"resource": resource})
            return True

    def release_lease(self, resource: str, job_id: str):
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            owner = db.execute(
                "SELECT job_id FROM leases WHERE resource=?", (resource,)
            ).fetchone()
            if owner and owner[0] != job_id:
                raise ValueError("lease belongs to another job")
            if owner:
                db.execute("DELETE FROM leases WHERE resource=?", (resource,))
                self._event(db, job_id, "LEASE_RELEASED", {"resource": resource})

    def recover(self, job_id: str):
        """Explicit recovery after the controller has terminated old processes."""
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            job = self._job(
                db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
            )
            if job["status"] == "ACCEPTED":
                raise ValueError("terminal job cannot recover")
            now = time.time()
            remaining, recovered_charge = job["remaining_seconds"], 0.0
            timings = {}
            for row in db.execute(
                "SELECT payload FROM events WHERE job_id=? AND kind='ATTEMPT_RESERVED' ORDER BY id",
                (job_id,),
            ):
                payload = json.loads(row["payload"])
                timings[payload["attempt_id"]] = payload
            for row in db.execute(
                "SELECT id FROM attempts WHERE job_id=? AND status='RUNNING'", (job_id,)
            ):
                elapsed, accounting = _recovered_seconds(
                    timings.get(row["id"]), remaining
                )
                remaining = max(0.0, remaining - elapsed)
                recovered_charge += elapsed
                proof = {
                    "reason": "controller interruption; requalification required",
                    "budget_accounting": accounting,
                    "charged_seconds": elapsed,
                }
                db.execute(
                    "UPDATE attempts SET status='INTERRUPTED',finished=?,evidence=?,elapsed_seconds=? WHERE id=?",
                    (now, _json(proof), elapsed, row["id"]),
                )
            for reservation_id, timing in self._pending_time(db, job_id).items():
                elapsed, accounting = _recovered_seconds(timing, remaining)
                remaining = max(0.0, remaining - elapsed)
                recovered_charge += elapsed
                self._event(
                    db,
                    job_id,
                    "TIME_FINISHED",
                    {
                        "reservation_id": reservation_id,
                        "elapsed_seconds": elapsed,
                        "interrupted": True,
                        "budget_accounting": accounting,
                    },
                )
            db.execute(
                "UPDATE jobs SET charged_seconds=charged_seconds+? WHERE id=?",
                (recovered_charge, job_id),
            )
            db.execute("DELETE FROM leases WHERE job_id=?", (job_id,))
            status = (
                "CANCELLED"
                if job["status"] == "CANCELLED"
                else ("BLOCKED" if remaining <= 0 else "WAITING_INPUT")
            )
            db.execute(
                "UPDATE jobs SET status=?,updated=? WHERE id=?", (status, now, job_id)
            )
            self._event(
                db,
                job_id,
                "RECOVERED",
                {
                    "requalification_required": status != "CANCELLED",
                    "charged_seconds": recovered_charge,
                },
            )
        return self.get_job(job_id)
