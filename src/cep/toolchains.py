"""Operator-owned executable bindings; qualification never grants subprocesses."""

from __future__ import annotations

import hashlib
import math
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile
import time

from .sandbox import NativeSandbox


def executable_digest(path: Path) -> str:
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_nlink != 1
            or not info.st_mode & 0o111
            or info.st_mode & 0o022
            or info.st_size > 250_000_000
        ):
            raise ValueError(
                "Tool executable must be bounded, regular, executable and not group/world writable"
            )
        digest = hashlib.sha256()
        while block := os.read(fd, 1_048_576):
            digest.update(block)
        return digest.hexdigest()
    finally:
        os.close(fd)


def validate_bindings(rows: object, repo: Path) -> tuple[Path, ...]:
    if not isinstance(rows, list) or len(rows) > 16:
        raise ValueError("Tool bindings must be a bounded array")
    seen, paths = set(), []
    for row in rows:
        if not isinstance(row, dict) or set(row) != {"name", "executable", "sha256"}:
            raise ValueError("Tool binding requires name, executable and sha256")
        name, executable, digest = row["name"], row["executable"], row["sha256"]
        if (
            not isinstance(name, str)
            or not re.fullmatch(r"[a-z][a-z0-9_-]{0,63}", name)
            or name in seen
        ):
            raise ValueError("Unique tool binding names required")
        if not isinstance(executable, str) or not Path(executable).is_absolute():
            raise ValueError("Tool executable must be operator-resolved and absolute")
        path = Path(executable)
        if (
            path.is_symlink()
            or path.resolve(strict=True) != path
            or path.is_relative_to(repo.resolve())
        ):
            raise ValueError(
                "Tool executable must be canonical and outside the worker repository"
            )
        if (
            not isinstance(digest, str)
            or not re.fullmatch(r"[0-9a-f]{64}", digest)
            or executable_digest(path) != digest
        ):
            raise ValueError("Tool executable changed; requalification required")
        seen.add(name)
        paths.append(path)
    return tuple(paths)


def qualify_toolchains(
    *, binaries: dict[str, Path] | None = None, timeout_seconds: float = 120
) -> dict:
    if (
        isinstance(timeout_seconds, bool)
        or not isinstance(timeout_seconds, (int, float))
        or not math.isfinite(timeout_seconds)
        or timeout_seconds <= 0
    ):
        raise ValueError("Positive qualification budget required")
    if binaries is None:
        binaries = {"python": Path(sys.executable).resolve()}
        for name in ("node", "uv"):
            if executable := shutil.which(name):
                binaries[name] = Path(executable).resolve()
    if not isinstance(binaries, dict) or not 1 <= len(binaries) <= 16:
        raise ValueError("At least one bounded toolchain binding required")
    recipes = {
        "python": [
            ["--version"],
            ["-I", "-c", "import json; print(json.dumps({'ok': True}))"],
        ],
        "node": [["--version"], ["-e", "console.log(JSON.stringify({ok:true}))"]],
        "uv": [["--version"]],
        "go": [["version"]],
    }
    deadline, rows = time.monotonic() + timeout_seconds, []
    sandbox = NativeSandbox()
    with tempfile.TemporaryDirectory(prefix="cep-tools-") as directory:
        root = Path(directory).resolve()
        repo = root / "repo"
        repo.mkdir()
        for name, path in binaries.items():
            if name not in recipes:
                raise ValueError("Unknown qualification recipe")
            path = Path(path).resolve(strict=True)
            before = executable_digest(path)
            probes = []
            for index, arguments in enumerate(recipes[name]):
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise ValueError("Toolchain qualification budget exhausted")
                scratch = root / (name + "-" + str(index))
                scratch.mkdir()
                result = sandbox.run(
                    [str(path), *arguments],
                    repo,
                    scratch,
                    min(10, remaining),
                    readable=(path,),
                )
                passed = (
                    result["exit_code"] == 0
                    and not result["timed_out"]
                    and not result["output_exceeded"]
                    and bool(result["stdout"].strip())
                )
                if index:
                    passed = (
                        passed and result["stdout"].strip() == '{"ok":true}'
                        if name == "node"
                        else passed and result["stdout"].strip() == '{"ok": true}'
                    )
                probes.append(
                    {
                        "id": "version" if index == 0 else "in-process-json",
                        "passed": passed,
                        "result": result,
                    }
                )
            unchanged = executable_digest(path) == before
            rows.append(
                {
                    "binding": {
                        "name": name,
                        "executable": str(path),
                        "sha256": before,
                    },
                    "passed": unchanged and all(p["passed"] for p in probes),
                    "probes": probes,
                    "capabilities": {
                        "version": probes[0]["passed"],
                        "in_process": len(probes) > 1 and probes[-1]["passed"],
                        "subprocesses": False,
                        "package_install": False,
                    },
                }
            )
    return {
        "schema_version": 1,
        "backend": "macos-seatbelt-no-fork",
        "passed": all(row["passed"] for row in rows),
        "tools": rows,
        "limitations": [
            "Fork-dependent commands remain blocked",
            "Version discovery alone does not qualify builds or tests",
            "Bindings grant read access to exact executable files only",
        ],
    }
