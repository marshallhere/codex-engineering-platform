"""Fixed disposable UID experiments; never an installable CEP backend."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import pwd
import resource
import secrets
import signal
import stat
import sys
import time

# Import only this protected sibling in the privileged workflow staging directory.
if __package__:
    from .uid_domain import InventoryError, inventory_uid
else:
    from uid_domain import InventoryError, inventory_uid


def prerequisites() -> dict:
    return {
        "platform": sys.platform,
        "root": os.getuid() == 0 and os.geteuid() == 0,
        "disposable_ci": os.environ.get("GITHUB_ACTIONS") == "true"
        and os.environ.get("RUNNER_ENVIRONMENT") == "github-hosted"
        and os.environ.get("CEP_UID_EXPERIMENT") == "disposable-v1",
        "production_qualified": False,
    }


def guard() -> None:
    checks = prerequisites()
    if checks["platform"] != "darwin" or not checks["root"] or not checks["disposable_ci"]:
        raise RuntimeError("qualification requires explicit disposable GitHub-hosted macOS CI")
    for path in (Path(__file__).resolve(), Path(__file__).resolve().with_name("uid_domain.py")):
        info = path.stat()
        parent = path.parent.stat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0
                or info.st_mode & 0o022 or info.st_nlink != 1
                or parent.st_uid != 0 or stat.S_IMODE(parent.st_mode) != 0o700):
            raise RuntimeError("experiment code requires private root-owned staging")


def drop(uid: int) -> None:
    if not 62000 <= uid < 65000 or os.getuid() != 0 or os.geteuid() != 0:
        raise RuntimeError("refusing unsafe fixture identity")
    resource.setrlimit(resource.RLIMIT_NPROC, (32, 32))
    resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    if os.getuid() != uid or os.geteuid() != uid or os.getgroups():
        raise RuntimeError("incomplete privilege drop")
    for restore in (os.setuid, os.seteuid):
        try:
            restore(0)
        except PermissionError:
            continue
        raise RuntimeError("fixture retained root identity")


def exclusive_lease() -> int:
    """Serialize all experiments in this disposable host; refuse unsafe aliases."""
    directory = Path("/private/var/run/cep-uid-experiments")
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = directory.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("unsafe disposable lease directory")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open("exclusive.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
                     0o600, dir_fd=directory_fd)
    finally:
        os.close(directory_fd)
    info = os.fstat(fd)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1 or info.st_mode & 0o077:
        os.close(fd)
        raise RuntimeError("unsafe disposable lease file")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError("another UID experiment holds the host lease") from None
    return fd


def choose_uid() -> int:
    for _ in range(100):
        uid = 62000 + secrets.randbelow(3000)
        try:
            pwd.getpwuid(uid)
        except KeyError:
            if not inventory_uid(uid):
                return uid
    raise RuntimeError("no unused fixture UID")


def fixture(mode: str, ready: int) -> None:
    """Only fixed, bounded fixtures; no operator/model supplied executable."""
    os.setsid()
    if mode == "detached":
        pid = os.fork()
        if pid:
            os._exit(0)
        os.setsid()
        pid = os.fork()
        if pid:
            os._exit(0)
        for fd in (0, 1, 2):
            try:
                os.close(fd)
            except OSError:
                pass
        os.write(ready, b"R")
        os.close(ready)
        time.sleep(30)
        os._exit(0)
    if mode == "posix-spawn":
        os.posix_spawn("/usr/bin/sleep", ["/usr/bin/sleep", "30"], {})
        os.write(ready, b"R")
        os.close(ready)
        time.sleep(30)
        os._exit(0)
    if mode == "concurrent-forks":
        # Readiness requires eight actual children, so an early cleanup cannot
        # accidentally turn this into a no-fork success. Forking then continues.
        for index in range(20):
            try:
                pid = os.fork()
            except OSError:
                break
            if pid == 0:
                os.setpgid(0, 0)
                time.sleep(30)
                os._exit(0)
            if index == 7:
                os.write(ready, b"R")
                os.close(ready)
            time.sleep(0.01)
        time.sleep(30)
        os._exit(0)
    raise RuntimeError("unknown fixed fixture")


def cleanup_child(uid: int) -> None:
    """Kernel permissions constrain every signal, including PID reuse races."""
    drop(uid)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            peers = [item for item in inventory_uid(uid) if item.pid != os.getpid()]
        except InventoryError:
            # Churn/zombies are not empty membership. The root fixture parent
            # concurrently reaps its own child; fail if metadata stays ambiguous.
            time.sleep(0.02)
            continue
        for item in peers:
            try:
                os.kill(item.pid, signal.SIGSTOP)
                os.kill(item.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if not peers:
            os._exit(0)
        time.sleep(0.02)
    os._exit(2)


def run_case(uid: int, mode: str) -> dict:
    read_fd, write_fd = os.pipe()
    worker = os.fork()
    if worker == 0:
        try:
            os.close(read_fd)
            drop(uid)
            fixture(mode, write_fd)
        except BaseException:
            os._exit(3)
    os.close(write_fd)
    os.set_blocking(read_fd, False)
    started = time.monotonic()
    ready = False
    cleaner = None
    worker_reaped = False
    try:
        while time.monotonic() - started < 3:
            try:
                if os.read(read_fd, 1) == b"R":
                    ready = True
                    break
            except BlockingIOError:
                pass
            time.sleep(0.01)
        if not ready:
            raise RuntimeError("fixture failed before readiness")
        discovered = len(inventory_uid(uid))
        minimum = 9 if mode == "concurrent-forks" else 2 if mode == "posix-spawn" else 1
        if discovered < minimum:
            raise RuntimeError("live fixture descendants missing from UID inventory")
    finally:
        os.close(read_fd)
        cleaner = os.fork()
        if cleaner == 0:
            try:
                cleanup_child(uid)
            except BaseException:
                os._exit(3)
        deadline = time.monotonic() + 8
        cleaner_status = None
        while time.monotonic() < deadline:
            if not worker_reaped:
                result, _ = os.waitpid(worker, os.WNOHANG)
                worker_reaped = result == worker
            if cleaner_status is None:
                result, status = os.waitpid(cleaner, os.WNOHANG)
                if result == cleaner:
                    cleaner_status = status
            if cleaner_status is not None and worker_reaped and not inventory_uid(uid):
                break
            time.sleep(0.02)
        survivors = inventory_uid(uid)
        if cleaner_status != 0 or not worker_reaped or survivors:
            raise RuntimeError("UID cleanup failed; domain quarantined, no reuse permitted")
    return {"case": mode, "ready": ready, "discovered": discovered,
            "survivors": 0, "elapsed_seconds": round(time.monotonic() - started, 3)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    report = prerequisites()
    if args.inspect and not args.qualify:
        report["qualification"] = "blocked: experimental privileged probes not activated"
        print(json.dumps(report, sort_keys=True))
        return 0
    if not args.qualify or args.inspect:
        parser.error("choose exactly one of --inspect or --qualify")
    try:
        guard()
        # Private staging serializes this fixed invocation. Each case gets a fresh
        # unused UID; failed domains are never selected again in this process.
        lease_fd = exclusive_lease()
        try:
            report["cases"] = [run_case(choose_uid(), mode)
                               for mode in ("detached", "posix-spawn", "concurrent-forks")]
        finally:
            os.close(lease_fd)
        report["experiment"] = "passed"
        report["qualification"] = "blocked: production containment not established"
        print(json.dumps(report, sort_keys=True))
        return 0
    except (OSError, RuntimeError) as exc:
        report["experiment"] = "failed"
        report["error"] = str(exc)
        print(json.dumps(report, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
