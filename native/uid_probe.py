"""Fixed disposable UID experiments; never an installable CEP backend."""

from __future__ import annotations

import argparse
import fcntl
import grp
import json
import os
from pathlib import Path
import pwd
import resource
import secrets
import select
import signal
import stat
import sys
import time

# Import only this protected sibling in the privileged workflow staging directory.
if __package__:
    from .uid_domain import InventoryError, credential_groups, inventory_uid
    from . import uid_journal
else:
    from uid_domain import InventoryError, credential_groups, inventory_uid
    import uid_journal

JOURNAL_DIRECTORY = Path("/private/var/run/cep-uid-experiments")


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
    if (
        checks["platform"] != "darwin"
        or not checks["root"]
        or not checks["disposable_ci"]
    ):
        raise RuntimeError(
            "qualification requires explicit disposable GitHub-hosted macOS CI"
        )
    for path in (
        Path(__file__).resolve(),
        Path(__file__).resolve().with_name("uid_domain.py"),
        Path(__file__).resolve().with_name("uid_journal.py"),
    ):
        info = path.stat()
        parent = path.parent.stat()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != 0
            or info.st_mode & 0o022
            or info.st_nlink != 1
            or parent.st_uid != 0
            or stat.S_IMODE(parent.st_mode) != 0o700
        ):
            raise RuntimeError("experiment code requires private root-owned staging")


def drop(uid: int) -> None:
    if not 62000 <= uid < 65000 or os.getuid() != 0 or os.geteuid() != 0:
        raise RuntimeError("refusing unsafe fixture identity")

    def setup(name, function, *arguments):
        try:
            function(*arguments)
        except OSError as exc:
            raise RuntimeError(f"privilege setup {name}: {exc}") from exc

    setup("RLIMIT_NPROC", resource.setrlimit, resource.RLIMIT_NPROC, (32, 32))
    setup("RLIMIT_NOFILE", resource.setrlimit, resource.RLIMIT_NOFILE, (64, 64))
    setup("RLIMIT_CORE", resource.setrlimit, resource.RLIMIT_CORE, (0, 0))
    setup("setgroups", os.setgroups, [])
    setup("setgid", os.setgid, uid)
    setup("setuid", os.setuid, uid)
    # Query actual process credentials rather than the account-directory extension.
    groups = credential_groups()
    if (
        os.getuid() != uid
        or os.geteuid() != uid
        or os.getgid() != uid
        or os.getegid() != uid
        or groups != [uid]
    ):
        raise RuntimeError(
            f"incomplete privilege drop: uid={os.getuid()} "
            f"euid={os.geteuid()} gid={os.getgid()} "
            f"egid={os.getegid()} groups={groups}"
        )
    for name, restore in (
        ("setuid", os.setuid),
        ("seteuid", os.seteuid),
        ("setgid", os.setgid),
        ("setegid", os.setegid),
    ):
        try:
            restore(0)
        except PermissionError:
            continue
        except OSError as exc:
            raise RuntimeError(
                f"root restoration {name} returned unexpected error: {exc}"
            ) from exc
        raise RuntimeError("fixture retained root identity")


def exclusive_lease() -> int:
    """Serialize all experiments in this disposable host; refuse unsafe aliases."""
    directory = JOURNAL_DIRECTORY
    try:
        directory.mkdir(mode=0o700)
    except FileExistsError:
        pass
    info = directory.lstat()
    if (
        not stat.S_ISDIR(info.st_mode)
        or info.st_uid != 0
        or stat.S_IMODE(info.st_mode) != 0o700
    ):
        raise RuntimeError("unsafe disposable lease directory")
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fd = os.open(
            "exclusive.lock",
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
    finally:
        os.close(directory_fd)
    info = os.fstat(fd)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_uid != 0
        or info.st_nlink != 1
        or info.st_mode & 0o077
    ):
        os.close(fd)
        raise RuntimeError("unsafe disposable lease file")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        raise RuntimeError("another UID experiment holds the host lease") from None
    return fd


def choose_uid() -> int:
    # The root journal survives flock release/controller death. Unknown records
    # fail the entire selection; stale reservations never become implicit reuse.
    reserved = uid_journal.reserved_uids(JOURNAL_DIRECTORY, expected_owner_uid=0)
    for _ in range(100):
        uid = 62000 + secrets.randbelow(3000)
        try:
            pwd.getpwuid(uid)
        except KeyError:
            try:
                grp.getgrgid(uid)
            except KeyError:
                if uid not in reserved and not inventory_uid(uid):
                    return uid
    raise RuntimeError("no unused fixture UID")


def release_verified(uid, reservation, result):
    """Release only after the case receipts and two fresh inventories pass."""
    if (
        not isinstance(result, dict)
        or type(result.get("error_count")) is not int
        or result.get("error_count") != 0
        or type(result.get("inventory_errors")) is not int
        or result.get("inventory_errors") != 0
        or type(result.get("cleaner_status")) is not int
        or result.get("cleaner_status") != 0
        or type(result.get("survivors")) is not int
        or result.get("survivors") != 0
        or type(result.get("worker_status")) is not int
        or result.get("worker_status") not in {0, int(signal.SIGKILL)}
    ):
        details = {"error_count": None, "inventory_errors": None, "errors": []}
        if isinstance(result, dict):
            details["error_count"] = result.get("error_count")
            details["inventory_errors"] = result.get("inventory_errors")
            errors = result.get("errors", [])
            if isinstance(errors, list):
                details["errors"] = [error for error in errors[:8] if type(error) is str]
        raise RuntimeError(
            "UID reservation remains quarantined after ambiguous cleanup: "
            + json.dumps(details, sort_keys=True)
        )
    snapshots = []
    for _ in range(2):
        processes = inventory_uid(uid)
        if processes:
            raise RuntimeError("UID reservation remains quarantined with live processes")
        observed = time.time_ns()
        if snapshots and observed <= snapshots[-1]["observed_at_ns"]:
            raise RuntimeError("UID inventory snapshots are not ordered")
        snapshots.append(
            {
                "id": os.urandom(16).hex(),
                "observed_at_ns": observed,
                "stable": True,
                "processes": [],
            }
        )
    uid_journal.release(
        JOURNAL_DIRECTORY,
        reservation,
        {
            "verified_empty": True,
            "reservation_uid": uid,
            "reservation_nonce": reservation.nonce,
            "snapshots": snapshots,
            "worker_exit_status": result["worker_status"],
            "expected_worker_status": result["worker_status"],
            "cleaner_exit_status": result["cleaner_status"],
        },
        expected_owner_uid=0,
    )


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
        os.posix_spawn("/bin/sleep", ["/bin/sleep", "30"], {})
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
    owned = set()

    def pipe():
        pair = os.pipe()
        owned.update(pair)
        return pair

    def close(fd):
        if fd in owned:
            owned.remove(fd)
            os.close(fd)

    try:
        read_fd, write_fd = pipe()
        worker_error_read, worker_error_write = pipe()
        worker = os.fork()
    except BaseException:
        for descriptor in tuple(owned):
            close(descriptor)
        raise
    if worker == 0:
        try:
            os.close(read_fd)
            os.close(worker_error_read)
            drop(uid)
            fixture(mode, write_fd)
        except BaseException as exc:
            try:
                os.write(
                    worker_error_write,
                    (type(exc).__name__ + ":" + str(exc)).encode()[:1024],
                )
            except OSError:
                pass
            os._exit(3)
    close(write_fd)
    close(worker_error_write)
    started = time.monotonic()
    ready = False
    discovered = None
    worker_error = ""
    cleaner_error = ""
    worker_status = None
    cleaner_status = None
    worker_reaped = False
    cleaner = None
    survivors = None
    error_read = None
    errors = []
    error_count = 0
    inventory_errors = 0
    failed = False

    def diagnostic(where, exc, *, fatal=True):
        nonlocal error_count, failed
        error_count += 1
        failed = failed or fatal
        if len(errors) < 8:
            errors.append(where + ":" + type(exc).__name__ + ":" + str(exc))

    try:
        os.set_blocking(worker_error_read, False)
        os.set_blocking(read_fd, False)
        while time.monotonic() - started < 3:
            try:
                message = os.read(read_fd, 1024)
                if message == b"R":
                    ready = True
                    break
                if not message:
                    worker_error = "worker exited before readiness"
                    break
            except BlockingIOError:
                pass
            time.sleep(0.01)
        if not ready:
            raise RuntimeError(f"fixture failed before readiness: {worker_error}")
        # A detached fixture deliberately exits its direct parent. Reap our own
        # exited child before inventory; zombies cannot supply BSD birth metadata.
        result, status = os.waitpid(worker, os.WNOHANG)
        if result == worker:
            worker_reaped, worker_status = True, status
        discovered = len(inventory_uid(uid))
        minimum = 9 if mode == "concurrent-forks" else 2 if mode == "posix-spawn" else 1
        if discovered < minimum:
            raise RuntimeError("live fixture descendants missing from UID inventory")
    except BaseException as exc:
        diagnostic("fixture", exc)
    finally:
        try:
            close(read_fd)
        except OSError as exc:
            diagnostic("ready-close", exc)
        try:
            error_read, error_write = pipe()
            cleaner = os.fork()
            if cleaner == 0:
                os.close(error_read)
                os.close(worker_error_read)
                try:
                    cleanup_child(uid)
                except BaseException as exc:
                    try:
                        os.write(
                            error_write,
                            (type(exc).__name__ + ":" + str(exc)).encode()[:1024],
                        )
                    except OSError:
                        pass
                    os._exit(3)
            close(error_write)
            os.set_blocking(error_read, False)
        except BaseException as exc:
            diagnostic("cleanup-launch", exc)
        # Only the dropped cleanup child signals peers. The root parent just
        # reaps its direct children and observes membership within this deadline.
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                if not worker_reaped:
                    try:
                        result, status = os.waitpid(worker, os.WNOHANG)
                        if result == worker:
                            worker_reaped, worker_status = True, status
                    except OSError as exc:
                        diagnostic("worker-wait", exc)
                if cleaner is not None and cleaner_status is None:
                    try:
                        result, status = os.waitpid(cleaner, os.WNOHANG)
                        if result == cleaner:
                            cleaner_status = status
                    except OSError as exc:
                        diagnostic("cleaner-wait", exc)
                try:
                    survivors = inventory_uid(uid)
                except InventoryError as exc:
                    survivors = None
                    inventory_errors += 1
                    diagnostic("inventory", exc, fatal=False)
                if cleaner_status is not None and worker_reaped and survivors == []:
                    break
                time.sleep(0.02)
        except BaseException as exc:
            survivors = None
            diagnostic("cleanup-observation", exc)
        finally:
            # Unknown membership never bypasses diagnostic collection or closes.
            try:
                readable, _, _ = select.select([worker_error_read], [], [], 0)
                text = (
                    os.read(worker_error_read, 1024).decode("utf-8", "replace")
                    if readable
                    else "worker diagnostic pipe remains open"
                )
                if text:
                    worker_error = text
            except BlockingIOError:
                pass
            except (OSError, ValueError) as exc:
                diagnostic("worker-diagnostic", exc)
            if error_read is not None:
                try:
                    readable, _, _ = select.select([error_read], [], [], 0)
                    cleaner_error = (
                        os.read(error_read, 1024).decode("utf-8", "replace")
                        if readable
                        else "cleanup diagnostic pipe remains open"
                    )
                except BlockingIOError:
                    cleaner_error = "cleanup still running"
                except (OSError, ValueError) as exc:
                    diagnostic("cleaner-diagnostic", exc)
            for descriptor in tuple(owned):
                try:
                    close(descriptor)
                except OSError as exc:
                    diagnostic("descriptor-close", exc)
    expected_worker_status = 0 if mode == "detached" else int(signal.SIGKILL)
    if (
        failed
        or not ready
        or worker_error
        or cleaner_error
        or cleaner_status != 0
        or not worker_reaped
        or survivors != []
        or worker_status != expected_worker_status
    ):
        raise RuntimeError(
            "UID cleanup failed; domain quarantined, no reuse permitted; "
            f"case={mode} worker_status={worker_status} worker_error={worker_error!r} "
            f"cleaner_status={cleaner_status} cleaner_error={cleaner_error!r} "
            f"survivors={'unknown' if survivors is None else len(survivors)} "
            f"error_count={error_count} inventory_errors={inventory_errors} errors={errors!r}"
        )
    return {
        "case": mode,
        "ready": ready,
        "discovered": discovered,
        "worker_status": worker_status,
        "cleaner_status": cleaner_status,
        "error_count": error_count,
        "inventory_errors": inventory_errors,
        "errors": errors[:8],
        "survivors": 0,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inspect", action="store_true")
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    report = prerequisites()
    if args.inspect and not args.qualify:
        report["qualification"] = (
            "blocked: experimental privileged probes not activated"
        )
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
            report["cases"] = []
            for mode in ("detached", "posix-spawn", "concurrent-forks"):
                uid = choose_uid()
                reservation = uid_journal.reserve(
                    JOURNAL_DIRECTORY, uid, expected_owner_uid=0
                )
                result = run_case(uid, mode)
                report["cases"].append(result)
                release_verified(uid, reservation, result)
                report["cases"][-1]["reservation_released"] = True
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
