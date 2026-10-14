#!/usr/bin/env python3
"""Fail-closed publication scan of Git history, index and tracked working files.

Reports locations and finding kinds only; never prints matching secret values.
This is a bounded pattern scanner, not a guarantee that arbitrary secrets cannot
exist. See docs/LOCAL_SETUP.md for supported checks and narrow fixture exceptions.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import stat
import subprocess


MAX_BYTES = 32 * 1024 * 1024
_RULES = {
    "private-key": re.compile(r"-----BEGIN (?:[A-Z0-9]+ )?PRIVATE KEY-----"),
    "stripe-secret": re.compile(
        r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{12,}\b|\bwhsec_[A-Za-z0-9]{12,}\b"
    ),
    "openai-secret": re.compile(r"\bsk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}\b"),
    "github-secret": re.compile(
        r"\bgh[pousr]_[A-Za-z0-9]{20,}\b|\bgithub_pat_[A-Za-z0-9_]{20,}\b"
    ),
    "provider-secret": re.compile(
        r"\bglpat-[A-Za-z0-9_-]{16,}\b|\bre_[A-Za-z0-9]{20,}\b|\bxox[baprs]-[A-Za-z0-9-]{16,}\b"
    ),
    "aws-access-key": re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b"),
    "jwt-token": re.compile(
        r"\beyJ[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\.[A-Za-z0-9_-]{6,}\b"
    ),
    "url-credential": re.compile(
        r"(?:https?|postgres(?:ql)?|mysql|redis)://[A-Za-z0-9._~-]+:[A-Za-z0-9._~!$&()+,;=:%-]+@"
    ),
    "bearer-token": re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{16,}", re.I),
    "machine-user-path": re.compile(r"/(?:Users|home)/[^\s/<>\"'`]+"),
}
_ASSIGNMENT = re.compile(r"""(?ix)
    ["']?\b(?:[a-z0-9_]*(?:api[_-]?key|access[_-]?token|auth[_-]?token|client[_-]?secret|password|secret|token))\b["']?
    \s*[:=]\s*["']([^"'\r\n]{8,})["']
""")
_IP = re.compile(r"(?<![0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![0-9.])")
_PRIVATE_NETWORKS = tuple(
    ipaddress.ip_network(v)
    for v in ((0x0A000000, 8), (0xAC100000, 12), (0xC0A80000, 16), (0xA9FE0000, 16))
)
_PLACEHOLDERS = {
    "replace_me",
    "changeme",
    "your-api-key",
    "your_api_key",
    "your-token",
    "your_token",
    "your-password",
    "your_password",
    "placeholder",
    "example-secret",
    "example-token",
    "dummy-password",
}
_EXAMPLE_USERS = {"me", "user", "example", "username"}


def _placeholder(value: str) -> bool:
    lowered = value.lower()
    return lowered in _PLACEHOLDERS or bool(
        re.fullmatch(r"<[^<>]+>|\$\{[A-Z][A-Z0-9_]*\}", value)
    )


def _scan(data: bytes) -> list[dict]:
    findings = []
    for line_number, line in enumerate(
        data.decode("utf-8", errors="replace").splitlines(), 1
    ):
        kinds = set()
        for kind, pattern in _RULES.items():
            for match in pattern.finditer(line):
                if (
                    kind == "machine-user-path"
                    and match.group().rsplit("/", 1)[-1] in _EXAMPLE_USERS
                ):
                    continue
                kinds.add(kind)
        for match in _ASSIGNMENT.finditer(line):
            if not _placeholder(match.group(1)):
                kinds.add("secret-assignment")
        for match in _IP.finditer(line):
            try:
                address = ipaddress.ip_address(match.group())
            except ValueError:
                continue
            if any(address in network for network in _PRIVATE_NETWORKS):
                # This exact documented fixture is the only RFC1918 exemption.
                if str(address) == "10.0.0.1" and "publication: dummy-ip" in line:
                    continue
                kinds.add("private-ip")
        findings.extend({"line": line_number, "kind": kind} for kind in sorted(kinds))
    return findings


def _git(root: Path, *args: str, input: bytes | None = None) -> bytes:
    environment = dict(os.environ)
    environment.update(
        GIT_OPTIONAL_LOCKS="0",
        GIT_TERMINAL_PROMPT="0",
        GIT_NO_REPLACE_OBJECTS="1",
        GIT_NO_LAZY_FETCH="1",
    )
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        input=input,
        capture_output=True,
        env=environment,
        timeout=60,
    )
    if result.returncode:
        # Git stderr can include paths or configured remote credentials.
        raise ValueError("git inspection failed")
    return result.stdout


def _label(path: str) -> str:
    if _scan(path.encode()):
        return "<redacted-path>"
    return "".join(c if c.isprintable() else "?" for c in path)[:300]


def _read_worktree(root: Path, relative: str) -> bytes | None:
    """Read a tracked entry with no-follow directory descriptors throughout."""
    fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        parts = Path(relative).parts
        for part in parts[:-1]:
            next_fd = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = next_fd
        info = os.stat(parts[-1], dir_fd=fd, follow_symlinks=False)
        if stat.S_ISLNK(info.st_mode):
            return os.readlink(parts[-1], dir_fd=fd).encode()
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("unscannable-working-file")
        file_fd = os.open(
            parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd
        )
        with os.fdopen(file_fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                raise ValueError("unscannable-working-file")
            data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("oversized-working-file")
        return data
    except FileNotFoundError:
        return None
    finally:
        os.close(fd)


def audit_repository(repository: Path) -> dict:
    """Inspect all reachable tracked history plus staged and tracked current data."""
    result = {
        "schema_version": 1,
        "status": "passed",
        "findings": [],
        "errors": [],
        "objects_scanned": 0,
        "working_files_scanned": 0,
        "coverage": ["reachable-history", "index", "tracked-worktree"],
        "limitations": [
            "pattern-based scanner; untracked files and unreachable objects are excluded",
            "external provider revocation and redistribution rights require separate review",
        ],
    }
    try:
        root = Path(repository).resolve(strict=True)
        if _git(root, "rev-parse", "--show-toplevel").decode().strip() != str(root):
            raise ValueError("supply the repository root")
        if _git(root, "rev-parse", "--is-shallow-repository").strip() == b"true":
            raise ValueError("shallow history cannot establish publication safety")
        object_paths: dict[str, str] = {}
        for line in _git(root, "rev-list", "--objects", "--all").splitlines():
            oid, _, path = line.partition(b" ")
            if not re.fullmatch(rb"[a-f0-9]{40,64}", oid):
                raise ValueError("unexpected Git object identifier")
            object_paths[oid.decode()] = (
                _label(path.decode("utf-8", errors="replace")) or "<commit-or-tag>"
            )
            for finding in _scan(path):
                result["findings"].append(
                    {
                        "scope": "history-path",
                        "object": oid.decode(),
                        "path": "<redacted-path>",
                        **finding,
                    }
                )
        index = _git(root, "ls-files", "--stage", "-z")
        paths = set()
        for record in index.split(b"\0"):
            if not record:
                continue
            metadata, separator, raw_path = record.partition(b"\t")
            if not separator:
                raise ValueError("invalid Git index record")
            mode, oid, stage = metadata.split()
            if stage != b"0":
                result["errors"].append({"kind": "unmerged-index"})
            path = raw_path.decode("utf-8", errors="strict")
            if Path(path).is_absolute() or ".." in Path(path).parts:
                raise ValueError("unsafe tracked path")
            for finding in _scan(raw_path):
                result["findings"].append(
                    {
                        "scope": "index-path",
                        "object": oid.decode(),
                        "path": "<redacted-path>",
                        **finding,
                    }
                )
            if mode == b"160000":
                result["errors"].append(
                    {"kind": "unscanned-submodule", "path": _label(path)}
                )
                continue
            object_paths.setdefault(oid.decode(), _label(path))
            paths.add(path)
        if object_paths:
            metadata = _git(
                root,
                "cat-file",
                "--batch-check=%(objectname) %(objecttype) %(objectsize)",
                input=("\n".join(object_paths) + "\n").encode(),
            )
            for row in metadata.decode().splitlines():
                parts = row.split()
                if len(parts) != 3 or parts[1] not in {"blob", "commit", "tag", "tree"}:
                    result["errors"].append({"kind": "missing-git-object"})
                    continue
                oid, kind, size = parts
                if int(size) > MAX_BYTES:
                    result["errors"].append(
                        {
                            "kind": "oversized-object",
                            "object": oid,
                            "path": object_paths.get(oid, "<object>"),
                        }
                    )
                    continue
                if kind == "tree":
                    # rev-list emits only one path for a reused blob. Inspect
                    # every tree entry so a deleted sensitive filename cannot
                    # hide behind identical contents at a harmless path.
                    entries = _git(root, "ls-tree", "-z", oid)
                    result["objects_scanned"] += 1
                    for entry in entries.split(b"\0"):
                        if not entry:
                            continue
                        entry_metadata, separator, filename = entry.partition(b"\t")
                        if not separator:
                            raise ValueError("invalid tree entry")
                        if entry_metadata.startswith(b"160000 "):
                            result["errors"].append(
                                {
                                    "kind": "unscanned-submodule",
                                    "object": oid,
                                    "path": _label(
                                        filename.decode("utf-8", errors="replace")
                                    ),
                                }
                            )
                        for finding in _scan(filename):
                            result["findings"].append(
                                {
                                    "scope": "history-path",
                                    "object": oid,
                                    "path": "<redacted-path>",
                                    **finding,
                                }
                            )
                    continue
                data = _git(root, "cat-file", kind, oid)
                result["objects_scanned"] += 1
                for finding in _scan(data):
                    result["findings"].append(
                        {
                            "scope": "history-or-index",
                            "object": oid,
                            "path": object_paths.get(oid, "<object>"),
                            **finding,
                        }
                    )
        for relative in sorted(paths):
            try:
                data = _read_worktree(root, relative)
            except (OSError, ValueError):
                result["errors"].append(
                    {"kind": "unscannable-working-file", "path": _label(relative)}
                )
                continue
            if data is None:
                continue
            result["working_files_scanned"] += 1
            for finding in _scan(data):
                result["findings"].append(
                    {"scope": "worktree", "path": _label(relative), **finding}
                )
    except (OSError, ValueError, UnicodeError, subprocess.SubprocessError) as exc:
        # Only our generic reasons are safe; never stringify OS/Git exceptions.
        reason = (
            str(exc)
            if isinstance(exc, ValueError)
            and str(exc)
            in {
                "git inspection failed",
                "supply the repository root",
                "shallow history cannot establish publication safety",
                "unexpected Git object identifier",
                "invalid Git index record",
                "unsafe tracked path",
            }
            else "inspection-failed"
        )
        result["errors"].append({"kind": reason})
    if result["findings"] or result["errors"]:
        result["status"] = "blocked"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("repository", type=Path, nargs="?", default=Path.cwd())
    args = parser.parse_args()
    result = audit_repository(args.repository)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
