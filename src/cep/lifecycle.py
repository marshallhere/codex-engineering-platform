"""Trusted birth-identity watchdogs for sandbox commands, outside worker access."""

from __future__ import annotations

import ctypes
import json
import math
import os
from pathlib import Path
import platform
import select
import signal
import stat
import subprocess
import sys
import time
import uuid

_WATCHDOGS = {}
MAX_RECORD = 16_384


class _BSDInfo(ctypes.Structure):
    # Darwin SDK sys/proc_info.h, PROC_PIDTBSDINFO (3), 136 bytes.
    _fields_ = [
        (name, ctypes.c_uint32)
        for name in (
            "flags",
            "status",
            "xstatus",
            "pid",
            "ppid",
            "uid",
            "gid",
            "ruid",
            "rgid",
            "svuid",
            "svgid",
            "reserved",
        )
    ] + [
        ("comm", ctypes.c_char * 16),
        ("name", ctypes.c_char * 32),
        ("nfiles", ctypes.c_uint32),
        ("pgid", ctypes.c_uint32),
        ("jobc", ctypes.c_uint32),
        ("tdev", ctypes.c_uint32),
        ("tpgid", ctypes.c_uint32),
        ("nice", ctypes.c_int32),
        ("start_seconds", ctypes.c_uint64),
        ("start_microseconds", ctypes.c_uint64),
    ]


def process_identity(pid: int) -> dict | None:
    """Inspect birth metadata only: no process environment, command, or arguments."""
    if type(pid) is not int or pid <= 1:
        raise ValueError("positive non-system PID required")
    if platform.system() == "Darwin":
        lib = ctypes.CDLL("/usr/lib/libproc.dylib", use_errno=True)
        query = lib.proc_pidinfo
        query.argtypes = [
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_uint64,
            ctypes.c_void_p,
            ctypes.c_int,
        ]
        query.restype = ctypes.c_int
        info = _BSDInfo()
        size = query(pid, 3, 0, ctypes.byref(info), ctypes.sizeof(info))
        if size != ctypes.sizeof(info) or info.pid != pid or info.status == 5:
            return None
        return {
            "pid": pid,
            "pgid": info.pgid,
            "uid": info.uid,
            "birth": [info.start_seconds, info.start_microseconds],
        }
    if platform.system() == "Linux":
        try:
            root = Path(f"/proc/{pid}")
            text = (root / "stat").read_text()
            fields = text[text.rfind(")") + 2 :].split()
            if fields[0] == "Z":
                return None
            return {
                "pid": pid,
                "pgid": int(fields[2]),
                "uid": root.stat().st_uid,
                "birth": [int(fields[19])],
            }
        except (FileNotFoundError, ProcessLookupError):
            return None
    raise ValueError("strong PID birth identity is unsupported on this OS")


def _same(identity) -> bool:
    if not isinstance(identity, dict) or type(identity.get("pid")) is not int:
        return False
    try:
        return (
            identity == process_identity(identity["pid"])
            and identity["uid"] == os.getuid()
        )
    except (ValueError, OSError):
        return False


def _kill(identity) -> bool:
    if not _same(identity) or identity.get("pgid") != identity["pid"]:
        return False
    try:
        os.killpg(identity["pid"], signal.SIGKILL)
        return True
    except ProcessLookupError:
        return False


def _registry(path: Path, create=False) -> Path:
    path = Path(path).absolute()
    if create:
        path.mkdir(parents=True, exist_ok=True, mode=0o700)
    # All ancestors must be real directories: resolve must not conceal aliases.
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError("registry symlinks are forbidden")
    info = path.stat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != os.getuid()
        or info.st_mode & 0o077
    ):
        raise ValueError("registry must be owner-only and protected from workers")
    return path


def _name(value):
    if not isinstance(value, str):
        raise ValueError("invalid lifecycle record ID")
    try:
        if str(uuid.UUID(value)) != value:
            raise ValueError("invalid lifecycle record ID")
    except (AttributeError, ValueError) as error:
        raise ValueError("invalid lifecycle record ID") from error
    return value + ".json"


def _write(registry, record, create=False):
    fd = os.open(registry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    temporary = None
    try:
        name = _name(record["id"])
        if not create:
            existing = os.open(
                name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
            )
            try:
                info = os.fstat(existing)
                if (
                    not stat.S_ISREG(info.st_mode)
                    or info.st_nlink != 1
                    or info.st_uid != os.getuid()
                ):
                    raise ValueError("unsafe lifecycle record")
            finally:
                os.close(existing)
        temporary = str(uuid.uuid4()) + ".tmp"
        target = os.open(
            temporary,
            os.O_WRONLY | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=fd,
        )
        try:
            info = os.fstat(target)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
            ):
                raise ValueError("unsafe lifecycle record")
            data = json.dumps(record, sort_keys=True, allow_nan=False).encode()
            if len(data) > MAX_RECORD:
                raise ValueError("lifecycle record exceeds limit")
            with os.fdopen(target, "wb", closefd=False) as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            os.close(target)
        if create:
            os.link(
                temporary, name, src_dir_fd=fd, dst_dir_fd=fd, follow_symlinks=False
            )
            os.unlink(temporary, dir_fd=fd)
        else:
            os.replace(temporary, name, src_dir_fd=fd, dst_dir_fd=fd)
        temporary = None
        os.fsync(fd)
    finally:
        if temporary is not None:
            os.unlink(temporary, dir_fd=fd)
        os.close(fd)


def _read(registry, name):
    identifier = name.removesuffix(".json")
    if _name(identifier) != name:
        raise ValueError("invalid lifecycle filename")
    directory = os.open(registry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(
            name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory
        )
        try:
            info = os.fstat(fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != os.getuid()
                or info.st_mode & 0o077
                or info.st_size > MAX_RECORD
            ):
                raise ValueError("unsafe lifecycle record")
            with os.fdopen(fd, "rb", closefd=False) as handle:
                data = handle.read(MAX_RECORD + 1)
            if len(data) > MAX_RECORD:
                raise ValueError("oversized lifecycle record")
            record = json.loads(data)
            if (
                not isinstance(record, dict)
                or record.get("schema_version") != 1
                or record.get("id") != identifier
            ):
                raise ValueError("unsupported lifecycle record")
            deadline = record.get("deadline_monotonic")
            if (
                isinstance(deadline, bool)
                or not isinstance(deadline, (int, float))
                or not math.isfinite(deadline)
                or deadline <= 0
            ):
                raise ValueError("invalid lifecycle deadline")
            if record.get("status") not in {
                "STARTING",
                "RUNNING",
                "FINISHED",
                "CLEANED",
                "DEADLINE_KILLED",
                "IDENTITY_CHANGED",
                "TARGET_EXITED",
            }:
                raise ValueError("invalid lifecycle status")
            return record
        finally:
            os.close(fd)
    finally:
        os.close(directory)


def supervise(pid: int, registry: Path, timeout: float) -> dict:
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("positive finite watchdog timeout required")
    root = _registry(registry, create=True)
    identity = process_identity(pid)
    if identity is None:
        # A process that exited before registration needs no watchdog.
        return {"schema_version": 1, "status": "ALREADY_EXITED", "target": None}
    if identity["pgid"] != pid or identity["uid"] != os.getuid():
        raise ValueError("supervised target must be an owned process-group leader")
    identifier = str(uuid.uuid4())
    record = {
        "schema_version": 1,
        "id": identifier,
        "registry": str(root),
        "path": str(root / _name(identifier)),
        "target": identity,
        "deadline_monotonic": time.monotonic() + timeout,
        "status": "STARTING",
    }
    _write(root, record, create=True)
    source = Path(__file__).resolve().parents[1]
    bootstrap = "import sys; sys.path.insert(0,sys.argv[1]); from cep.lifecycle import _watch; _watch(sys.argv[2],sys.argv[3])"
    process = subprocess.Popen(
        [sys.executable, "-I", "-c", bootstrap, str(source), str(root), identifier],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env={"PATH": os.defpath},
        start_new_session=True,
    )
    _WATCHDOGS[identifier] = process
    watcher = process_identity(process.pid)
    if watcher is None or watcher["pgid"] != process.pid:
        _kill(identity)
        raise ValueError("watchdog failed to start")
    record.update(watchdog=watcher, status="RUNNING")
    _write(root, record)
    return record


def _watch(registry: str, identifier: str):
    root = _registry(Path(registry))
    # Wait for parent to persist the watchdog identity, but never indefinitely.
    registration_deadline = time.monotonic() + 2
    while True:
        try:
            record = _read(root, _name(identifier))
        except (ValueError, OSError):
            if time.monotonic() >= registration_deadline:
                return
            time.sleep(0.02)
            continue
        if record["status"] == "STARTING":
            if time.monotonic() >= min(
                registration_deadline, record["deadline_monotonic"]
            ):
                _kill(record["target"])
                return
            time.sleep(0.02)
            continue
        if record["status"] != "RUNNING":
            return
        break
    target = record["target"]
    while _same(target):
        remaining = record["deadline_monotonic"] - time.monotonic()
        if remaining <= 0:
            killed = _kill(target)
            record.update(status="DEADLINE_KILLED" if killed else "IDENTITY_CHANGED")
            _write(root, record)
            return
        time.sleep(min(0.05, remaining))
    record.update(status="TARGET_EXITED")
    _write(root, record)


def finish(record: dict) -> None:
    if record.get("status") == "ALREADY_EXITED":
        return
    root = _registry(Path(record["registry"]))
    current = _read(root, _name(record["id"]))
    if current.get("target") != record.get("target"):
        raise ValueError("lifecycle target identity changed")
    _kill(current.get("watchdog"))
    process = _WATCHDOGS.pop(record["id"], None)
    if process is not None:
        process.wait(timeout=2)
    current["status"] = "FINISHED"
    _write(root, current)


def cleanup_registry(registry: Path) -> list[dict]:
    try:
        registry.lstat()
    except FileNotFoundError:
        return []
    root = _registry(registry)
    results = []
    for path in sorted(root.glob("*.json")):
        try:
            record = _read(root, path.name)
            killed = (
                _kill(record.get("target"))
                if record["status"] in {"STARTING", "RUNNING"}
                else False
            )
            watcher_killed = _kill(record.get("watchdog"))
            process = _WATCHDOGS.pop(record["id"], None)
            if process is not None:
                process.wait(timeout=2)
            record["status"] = "CLEANED"
            _write(root, record)
            results.append(
                {
                    "id": record["id"],
                    "target_killed": killed,
                    "watchdog_killed": watcher_killed,
                }
            )
        except (ValueError, OSError, subprocess.TimeoutExpired) as error:
            results.append({"file": path.name, "error": str(error)})
    return results


class GuardedProcess:
    """Minimal binary-pipe process handle for a supervised fork/exec child."""

    def __init__(self, pid, stdout_fd, stderr_fd, registration):
        self.pid = pid
        self.stdout = os.fdopen(stdout_fd, "rb", buffering=0)
        self.stderr = os.fdopen(stderr_fd, "rb", buffering=0)
        self.registration = registration
        self.returncode = None

    def poll(self):
        if self.returncode is None:
            waited, status = os.waitpid(self.pid, os.WNOHANG)
            if waited:
                self.returncode = os.waitstatus_to_exitcode(status)
        return self.returncode

    def wait(self, timeout=None):
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout)
            or timeout < 0
        ):
            raise ValueError("finite nonnegative wait timeout required")
        deadline = None if timeout is None else time.monotonic() + timeout
        while self.poll() is None:
            if deadline is not None and time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired("guarded process", timeout)
            time.sleep(0.01)
        return self.returncode


def guarded_popen(argv, cwd, env, registry, timeout, *, before_release=None):
    """Never execute worker argv until the independent watchdog is durable.

    ``before_release`` is a trusted fault-injection callback, called after READY
    and before registration. It is not exposed by any worker tool.
    """
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(arg, str) or not arg or "\0" in arg for arg in argv)
    ):
        raise ValueError("direct nonempty argv required")
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or timeout <= 0
    ):
        raise ValueError("positive finite process timeout required")
    directory = str(Path(cwd).resolve(strict=True))
    environment = dict(os.environ if env is None else env)
    # Validate protected location before even creating the held child.
    registry = _registry(Path(registry), create=True)
    out_read, out_write = os.pipe()
    err_read, err_write = os.pipe()
    ready_read, ready_write = os.pipe()
    release_read, release_write = os.pipe()
    descriptors = [
        out_read,
        out_write,
        err_read,
        err_write,
        ready_read,
        ready_write,
        release_read,
        release_write,
    ]
    try:
        pid = os.fork()
    except BaseException:
        for descriptor in descriptors:
            os.close(descriptor)
        raise
    if pid == 0:
        try:
            # Crucially drop the child's release writer: parent death becomes EOF.
            for descriptor in (out_read, err_read, ready_read, release_write):
                os.close(descriptor)
            os.setsid()
            os.dup2(out_write, 1)
            os.dup2(err_write, 2)
            os.close(out_write)
            os.close(err_write)
            null = os.open(os.devnull, os.O_RDONLY)
            os.dup2(null, 0)
            os.close(null)
            os.write(ready_write, b"READY")
            os.close(ready_write)
            readable, _, _ = select.select([release_read], [], [], 2)
            if not readable or os.read(release_read, 1) != b"\x01":
                os._exit(125)
            os.close(release_read)
            os.chdir(directory)
            os.execvpe(argv[0], argv, environment)
        except BaseException:
            os._exit(126)
    for descriptor in (out_write, err_write, ready_write, release_read):
        os.close(descriptor)
    registration = None
    try:
        readable, _, _ = select.select([ready_read], [], [], min(2, timeout))
        if not readable or os.read(ready_read, 5) != b"READY":
            raise ValueError("held worker failed to become ready")
        if before_release is not None:
            before_release(pid)
        registration = supervise(pid, registry, timeout)
        if registration.get("status") != "RUNNING":
            raise ValueError("held worker exited before registration")
        # Registration is atomic and fsynced before untrusted execution is released.
        os.write(release_write, b"\x01")
        return GuardedProcess(pid, out_read, err_read, registration)
    except BaseException:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        os.waitpid(pid, 0)
        os.close(out_read)
        os.close(err_read)
        if registration is not None:
            finish(registration)
        raise
    finally:
        os.close(ready_read)
        os.close(release_write)
