"""Bounded process groups and secret-minimal execution environments."""

from __future__ import annotations

import os
import math
import re
import selectors
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path


def clean_env(scratch: Path) -> dict[str, str]:
    scratch.mkdir(parents=True, exist_ok=True)
    tool_dirs = {str(Path(sys.executable).resolve().parent)}
    for name in ("node", "codex"):
        executable = shutil.which(name)
        if executable:
            tool_dirs.add(str(Path(executable).resolve().parent))
    return {
        "PATH": os.pathsep.join(sorted(tool_dirs)) + os.pathsep + os.defpath,
        "LANG": "en_US.UTF-8",
        "LC_ALL": "en_US.UTF-8",
        "HOME": str(scratch),
        "TMPDIR": str(scratch),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONNOUSERSITE": "1",
        "OPENSPEC_TELEMETRY": "0",
    }


def redact(text: str) -> str:
    text = re.sub(r"(?i)(bearer\s+)[\w.\-]+", r"\1[REDACTED]", text)
    text = re.sub(r"\b(?:sk|rk|pk)_(?:live|test)_[A-Za-z0-9]+\b", "[REDACTED]", text)
    text = re.sub(r"\b(?:ghp_|github_pat_)[A-Za-z0-9_]+\b", "[REDACTED]", text)
    return text


def run_process(
    argv: list[str],
    cwd: Path,
    timeout: float,
    *,
    env: dict | None = None,
    record_argv: list[str] | None = None,
    output_limit: int = 2_000_000,
    registry: Path | None = None,
) -> dict:
    if not argv or not all(isinstance(a, str) and a and "\0" not in a for a in argv):
        raise ValueError("Process requires nonempty string argv")
    if isinstance(timeout, bool) or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("Process requires remaining positive budget")
    start = time.monotonic()
    if registry is not None:
        from .lifecycle import guarded_popen

        proc = guarded_popen(argv, cwd, env, registry, timeout)
    else:
        proc = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
    timed_out, output_exceeded = False, False
    output = {"stdout": bytearray(), "stderr": bytearray()}
    count = 0
    selector = selectors.DefaultSelector()
    for name, pipe in (("stdout", proc.stdout), ("stderr", proc.stderr)):
        os.set_blocking(pipe.fileno(), False)
        selector.register(pipe, selectors.EVENT_READ, name)
    try:
        while selector.get_map() or proc.poll() is None:
            if time.monotonic() - start >= timeout:
                timed_out = True
                break
            if proc.poll() is not None:
                # A detached descendant retaining inherited pipes must not hold
                # the controller indefinitely. Drain only immediately available data.
                ready = selector.select(0)
                if not ready:
                    break
            else:
                ready = selector.select(
                    min(0.05, max(0.001, timeout - (time.monotonic() - start)))
                )
            for key, _ in ready:
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                count += len(data)
                output[key.data].extend(data)
                if len(output[key.data]) > 200000:
                    del output[key.data][:-200000]
                if count > output_limit:
                    output_exceeded = True
                    break
            if output_exceeded:
                break
    finally:
        # A successful direct child can leave background descendants behind too.
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        selector.close()
        proc.stdout.close()
        proc.stderr.close()
        proc.wait(timeout=2)
        if registry is not None:
            from .lifecycle import finish

            finish(proc.registration)
    return {
        "argv": [redact(a) for a in (record_argv or argv)],
        "exit_code": proc.returncode,
        "timed_out": timed_out,
        "output_exceeded": output_exceeded,
        "elapsed_seconds": time.monotonic() - start,
        "stdout": redact(output["stdout"].decode("utf-8", errors="replace")),
        "stderr": redact(output["stderr"].decode("utf-8", errors="replace")),
    }
