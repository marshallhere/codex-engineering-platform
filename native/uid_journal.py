"""Durable reservations for disposable UID experiments.

This module is a small filesystem primitive, not proof that a UID is unused or
that cleanup succeeded. Callers must establish those facts independently. A
reservation is fail-closed: any existing record, including an unreadable or
malformed one, keeps that UID unavailable until reviewed/repaired explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import secrets
import stat

MIN_UID = 62000
MAX_UID = 64999
MAX_RECORD_BYTES = 4096
_SCHEMA = 1
_DIR_MODE = 0o700
_FILE_MODE = 0o600


class JournalError(RuntimeError):
    """The reservation journal could not be safely read or changed."""


@dataclass(frozen=True)
class Reservation:
    uid: int
    nonce: str


def _uid(value: object) -> int:
    if type(value) is not int or not MIN_UID <= value <= MAX_UID:
        raise JournalError("UID is outside the permitted reservation range")
    return value


def _name(uid: int) -> str:
    return f"uid-{_uid(uid)}.json"


def _canonical(record: dict[str, object]) -> bytes:
    encoded = json.dumps(
        record, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("ascii")
    if len(encoded) > MAX_RECORD_BYTES:
        raise JournalError("journal record exceeds size limit")
    return encoded


def _directory_fd(directory: Path, expected_owner_uid: int) -> int:
    if type(expected_owner_uid) is not int or expected_owner_uid < 0:
        raise JournalError("invalid expected journal owner")
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(os.fspath(directory), flags)
        info = os.fstat(fd)
    except OSError as exc:
        raise JournalError("cannot securely open reservation directory") from exc
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != expected_owner_uid
        or stat.S_IMODE(info.st_mode) != _DIR_MODE
    ):
        os.close(fd)
        raise JournalError("reservation directory owner or mode is unsafe")
    return fd


def _read_record(directory_fd: int, uid: int, expected_owner_uid: int) -> dict[str, object]:
    name = _name(uid)
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise JournalError("reservation record is unavailable") from exc
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != expected_owner_uid
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != _FILE_MODE
            or info.st_size < 1
            or info.st_size > MAX_RECORD_BYTES
        ):
            raise JournalError("reservation record owner, type, mode, or size is unsafe")
        chunks: list[bytes] = []
        remaining = MAX_RECORD_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 1024))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(chunks)
        if len(raw) > MAX_RECORD_BYTES:
            raise JournalError("reservation record exceeds size limit")
        try:
            record = json.loads(raw.decode("ascii"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise JournalError("reservation record is malformed") from exc
        if type(record) is not dict or _canonical(record) != raw:
            raise JournalError("reservation record is not canonical JSON")
        if set(record) != {"schema", "uid", "nonce", "state"}:
            raise JournalError("reservation record has unexpected fields")
        if (
            type(record["schema"]) is not int
            or record["schema"] != _SCHEMA
            or type(record["uid"]) is not int
            or record["uid"] != uid
            or type(record["nonce"]) is not str
            or len(record["nonce"]) != 32
            or any(char not in "0123456789abcdef" for char in record["nonce"])
            or record["state"] != "reserved"
            or type(record["state"]) is not str
        ):
            raise JournalError("reservation record fields are invalid")
        return record
    finally:
        os.close(fd)


def _reserved_uids_fd(directory_fd: int, expected_owner_uid: int) -> set[int]:
    """Validate every reservation entry before returning its UID set."""
    try:
        names = os.listdir(directory_fd)
    except OSError as exc:
        raise JournalError("cannot enumerate reservation journal") from exc
    reserved: set[int] = set()
    for name in names:
        if not name.startswith("uid-"):
            continue
        match = re.fullmatch(r"uid-(0|[1-9][0-9]*)\.json", name)
        if match is None:
            raise JournalError("journal contains a malformed reservation name")
        try:
            uid = int(match.group(1))
        except ValueError as exc:
            raise JournalError("journal contains a malformed reservation name") from exc
        _uid(uid)
        _read_record(directory_fd, uid, expected_owner_uid)
        reserved.add(uid)
    return reserved


def reserved_uids(directory: Path, *, expected_owner_uid: int) -> set[int]:
    """Return all validated reservations; malformed entries fail closed.

    This is a filesystem ownership check, not proof of root authority or UID
    availability. Callers must still perform an independent process inventory.
    """
    directory_fd = _directory_fd(directory, expected_owner_uid)
    try:
        return _reserved_uids_fd(directory_fd, expected_owner_uid)
    finally:
        os.close(directory_fd)


def reserve(
    directory: Path, uid: int, *, expected_owner_uid: int
) -> Reservation:
    """Create and durably sync a reservation, failing if any name already exists.

    `expected_owner_uid` is a filesystem ownership assertion only. Tests may
    pass their temporary-directory owner; that does not model root authority.
    """
    uid = _uid(uid)
    directory_fd = _directory_fd(directory, expected_owner_uid)
    name = _name(uid)
    nonce = secrets.token_hex(16)
    record = {"schema": _SCHEMA, "uid": uid, "nonce": nonce, "state": "reserved"}
    payload = _canonical(record)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = -1
    try:
        _reserved_uids_fd(directory_fd, expected_owner_uid)
        try:
            fd = os.open(name, flags, _FILE_MODE, dir_fd=directory_fd)
        except FileExistsError as exc:
            raise JournalError("UID already has a reservation; fail closed") from exc
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != expected_owner_uid
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != _FILE_MODE
        ):
            raise JournalError("new reservation file owner or mode is unsafe")
        view = memoryview(payload)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise JournalError("short write creating reservation")
            view = view[written:]
        os.fsync(fd)
        os.fsync(directory_fd)
        return Reservation(uid=uid, nonce=nonce)
    except BaseException:
        # A partial record deliberately remains: it keeps the UID unavailable.
        raise
    finally:
        if fd >= 0:
            os.close(fd)
        os.close(directory_fd)


def _validate_evidence(evidence: object, reservation: Reservation) -> None:
    if type(evidence) is not dict or set(evidence) != {
        "verified_empty",
        "reservation_uid",
        "reservation_nonce",
        "snapshots",
        "worker_exit_status",
        "expected_worker_status",
        "cleaner_exit_status",
    }:
        raise JournalError("release evidence is missing or has unexpected fields")
    if (
        evidence["verified_empty"] is not True
        or type(evidence["reservation_uid"]) is not int
        or evidence["reservation_uid"] != reservation.uid
        or type(evidence["reservation_nonce"]) is not str
        or evidence["reservation_nonce"] != reservation.nonce
        or type(evidence["worker_exit_status"]) is not int
        or type(evidence["expected_worker_status"]) is not int
        or evidence["expected_worker_status"] not in {0, 9}
        or evidence["worker_exit_status"] != evidence["expected_worker_status"]
        or type(evidence["cleaner_exit_status"]) is not int
        or evidence["cleaner_exit_status"] != 0
    ):
        raise JournalError("release evidence does not prove successful empty cleanup")
    snapshots = evidence["snapshots"]
    if type(snapshots) is not list or len(snapshots) != 2:
        raise JournalError("release requires exactly two stable empty snapshots")
    identifiers: set[str] = set()
    for snapshot in snapshots:
        if type(snapshot) is not dict or set(snapshot) != {
            "id",
            "observed_at_ns",
            "stable",
            "processes",
        }:
            raise JournalError("snapshot evidence has unexpected fields")
        identifier = snapshot["id"]
        if (
            type(identifier) is not str
            or not identifier
            or identifier in identifiers
            or type(snapshot["observed_at_ns"]) is not int
            or snapshot["observed_at_ns"] <= 0
            or snapshot["stable"] is not True
            or type(snapshot["processes"]) is not list
            or snapshot["processes"]
        ):
            raise JournalError("snapshot evidence is not distinct, stable, and empty")
        identifiers.add(identifier)
    if snapshots[0]["observed_at_ns"] >= snapshots[1]["observed_at_ns"]:
        raise JournalError("snapshot observations are not in distinct chronological order")


def release(
    directory: Path,
    reservation: Reservation,
    evidence: object,
    *,
    expected_owner_uid: int,
) -> None:
    """Remove a matching reservation only after strict cleanup evidence checks."""
    if type(reservation) is not Reservation:
        raise JournalError("invalid reservation identity")
    uid = _uid(reservation.uid)
    if type(reservation.nonce) is not str or len(reservation.nonce) != 32:
        raise JournalError("invalid reservation nonce")
    if any(char not in "0123456789abcdef" for char in reservation.nonce):
        raise JournalError("invalid reservation nonce")
    _validate_evidence(evidence, reservation)

    directory_fd = _directory_fd(directory, expected_owner_uid)
    name = _name(uid)
    try:
        _reserved_uids_fd(directory_fd, expected_owner_uid)
        record = _read_record(directory_fd, uid, expected_owner_uid)
        if record["nonce"] != reservation.nonce:
            raise JournalError("reservation identity does not match journal")
        try:
            current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        except OSError as exc:
            raise JournalError("reservation changed during release") from exc
        if (
            not stat.S_ISREG(current.st_mode)
            or current.st_uid != expected_owner_uid
            or current.st_nlink != 1
        ):
            raise JournalError("reservation changed during release")
        try:
            os.unlink(name, dir_fd=directory_fd)
            os.fsync(directory_fd)
        except OSError as exc:
            raise JournalError("could not durably release reservation") from exc
    finally:
        os.close(directory_fd)
