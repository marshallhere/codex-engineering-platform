"""Native Codex Seatbelt execution, qualified by executable denial probes.

No hooks, MCPs or browser access are implied by successful shell qualification.
"""

from __future__ import annotations

import json
import platform
import os
import signal
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

from .process import clean_env, run_process


class NativeSandbox:
    def __init__(self, codex: str | None = None):
        self.codex = codex or shutil.which("codex")
        if platform.system() != "Darwin" or not self.codex:
            raise ValueError("Native live execution requires macOS and installed Codex")
        self.codex = str(Path(self.codex).resolve())

    def permissions(
        self,
        repo: Path,
        scratch: Path,
        *,
        writable: bool,
        readable: tuple[Path, ...] = (),
    ) -> dict:
        repo, scratch = repo.resolve(), scratch.resolve()
        roots = {
            ":minimal": "read",
            str(Path(sys.base_prefix).resolve()): "read",
            str(Path(sys.executable).resolve().parent): "read",
            str(repo): "write" if writable else "read",
            str(scratch): "write",
        }
        for p in readable:
            roots[str(p.resolve())] = "read"
        for protected in (
            ".git",
            ".codex",
            ".cep",
            "openspec",
            "tests",
            "test",
            "__tests__",
        ):
            roots[str(repo / protected)] = "read"
        return {"filesystem": roots, "network": {"enabled": False}}

    @staticmethod
    def override(policy: dict) -> str:
        # One inline TOML value avoids the CLI's literal quoting of dotted key segments.
        fs = ",".join(
            f"{json.dumps(k)}={json.dumps(v)}" for k, v in policy["filesystem"].items()
        )
        return "permissions.cep={filesystem={" + fs + "},network={enabled=false}}"

    def command(
        self,
        argv: list[str],
        repo: Path,
        scratch: Path,
        *,
        writable: bool = False,
        readable: tuple[Path, ...] = (),
    ) -> list[str]:
        argv = list(argv)
        if argv and Path(argv[0]).is_absolute():
            argv[0] = str(Path(argv[0]).resolve())
        roots = [
            Path("/System"),
            Path("/usr"),
            Path("/Library/Apple"),
            Path(sys.base_prefix).resolve(),
            Path(sys.executable).resolve().parent,
            repo.resolve(),
            scratch.resolve(),
            *[p.resolve() for p in readable],
        ]
        expressions = " ".join("(subpath " + json.dumps(str(p)) + ")" for p in roots)
        writes = "(subpath " + json.dumps(str(scratch.resolve())) + ")"
        if writable:
            writes += " (subpath " + json.dumps(str(repo.resolve())) + ")"
        protected = " ".join(
            "(subpath " + json.dumps(str(repo.resolve() / p)) + ")"
            for p in (
                ".git",
                ".codex",
                ".cep",
                "openspec",
                "tests",
                "test",
                "__tests__",
            )
        )
        profile = (
            "(version 1)(deny default)(allow process-exec)(deny process-fork)"
            "(allow file-read-metadata)(allow sysctl-read)"
            '(allow file-read-data (literal "/") '
            + expressions
            + ' (literal "/dev/null") (literal "/dev/urandom") (literal "/dev/random"))'
            "(allow file-write* " + writes + ' (literal "/dev/null"))'
            "(deny file-write* " + protected + ")"
            "(deny network*)(deny mach-lookup)"
        )
        return ["/usr/bin/sandbox-exec", "-p", profile, *argv]

    def run(
        self,
        argv: list[str],
        repo: Path,
        scratch: Path,
        timeout: float,
        *,
        writable: bool = False,
        readable: tuple[Path, ...] = (),
        registry: Path | None = None,
    ) -> dict:
        return run_process(
            self.command(argv, repo, scratch, writable=writable, readable=readable),
            repo,
            timeout,
            env=clean_env(scratch),
            registry=registry or scratch.parent / "registrations",
        )

    def qualify(
        self, parent: Path | None = None, *, timeout_seconds: float = 120
    ) -> dict:
        deadline = time.monotonic() + timeout_seconds
        results = []
        with tempfile.TemporaryDirectory(
            prefix="cep-qualify-", dir=parent
        ) as directory:
            root = Path(directory).resolve()
            work, scratch = root / "work", root / "scratch"
            work.mkdir()
            scratch.mkdir()
            protected = root / "protected"
            protected.write_text("probe")
            (work / "escape").symlink_to(protected)
            probes = [
                (
                    "project-write",
                    'from pathlib import Path; Path("allowed").write_text("ok")',
                    True,
                    True,
                ),
                (
                    "outside-read",
                    f"from pathlib import Path; Path({str(protected)!r}).read_text()",
                    True,
                    False,
                ),
                (
                    "outside-write",
                    f'from pathlib import Path; Path({str(protected)!r}).write_text("changed")',
                    True,
                    False,
                ),
                (
                    "symlink-read",
                    'from pathlib import Path; Path("escape").read_text()',
                    True,
                    False,
                ),
                (
                    "reviewer-write",
                    'from pathlib import Path; Path("denied").write_text("x")',
                    False,
                    False,
                ),
                (
                    "network-connect",
                    'import socket; socket.create_connection(("127.0.0.1",PORT),timeout=2)',
                    True,
                    False,
                ),
                (
                    "unix-socket",
                    "import socket; s=socket.socket(socket.AF_UNIX); s.connect(SOCKET)",
                    True,
                    False,
                ),
            ]
            listener = socket.socket()
            unix = socket.socket(socket.AF_UNIX)
            try:
                listener.bind(("127.0.0.1", 0))
                listener.listen()
                unix.bind(str(root / "socket"))
                unix.listen()
                for name, script, writable, expected in probes:
                    script = script.replace(
                        "PORT", str(listener.getsockname()[1])
                    ).replace("SOCKET", repr(str(root / "socket")))
                    r = self.run(
                        [sys.executable, "-I", "-c", script],
                        work,
                        scratch,
                        min(15, deadline - time.monotonic()),
                        writable=writable,
                    )
                    success = r["exit_code"] == 0
                    # Negative probes must specifically fail with a permission denial.
                    denied = "PermissionError" in r["stderr"]
                    passed = success if expected else (not success and denied)
                    results.append(
                        {
                            "id": name,
                            "passed": passed,
                            "exit_code": r["exit_code"],
                            "stderr": r["stderr"],
                            "elapsed_seconds": r["elapsed_seconds"],
                        }
                    )
            finally:
                listener.close()
                unix.close()
            # A process-group timeout alone is not descendant containment. Probe
            # a detached child and clean up only this disposable probe's recorded PID.
            pidfile = scratch / "detached.pid"
            script = (
                "import os,time,pathlib; p=os.fork(); "
                "\nif p == 0:\n os.setsid(); pathlib.Path("
                + repr(str(pidfile))
                + ").write_text(str(os.getpid())); os.close(1); os.close(2); time.sleep(15); os._exit(0)\n"
                "else:\n time.sleep(.2)\n"
            )
            detached = self.run(
                [sys.executable, "-I", "-c", script],
                work,
                scratch,
                min(3, deadline - time.monotonic()),
                writable=True,
            )
            contained = not pidfile.exists() and "PermissionError" in detached["stderr"]
            if pidfile.exists():
                pid = int(pidfile.read_text())
                try:
                    os.kill(pid, 0)
                except ProcessLookupError:
                    contained = True
                else:
                    os.kill(pid, signal.SIGKILL)
            results.append(
                {
                    "id": "detached-descendant-containment",
                    "passed": contained,
                    "exit_code": detached["exit_code"],
                    "detail": "Detached child survived process-group cleanup"
                    if not contained
                    else "fork denied by kernel",
                    "probe_cleanup": "only recorded disposable child PID",
                    "elapsed_seconds": detached["elapsed_seconds"],
                }
            )
            unchanged = protected.read_text() == "probe"
        version = run_process(
            [self.codex, "--version"], Path.cwd(), min(10, deadline - time.monotonic())
        )
        return {
            "backend": "macos-seatbelt-no-fork",
            "codex_version": version["stdout"].strip(),
            "passed": unchanged and all(x["passed"] for x in results),
            "probes": results,
            "capabilities": {
                "shell_filesystem_network": "qualified"
                if all(x["passed"] for x in results[:-1])
                else "blocked",
                "bounded_job_lifecycle": "qualified" if contained else "blocked",
                "process_fork": "not-granted",
                "mcp": "not-granted",
                "browser": "not-granted",
                "providers": "not-granted",
            },
        }
