"""Content-addressed candidates and immutable command evidence."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
from pathlib import Path


def digest_json(value: dict) -> str:
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    ).hexdigest()


def runtime_digest() -> str:
    root = Path(__file__).resolve().parent
    return digest_json(
        {
            p.name: hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.glob("*.py"))
        }
    )


def write_json(path: Path, value: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, sort_keys=True, indent=2, allow_nan=False)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _git_run(repo: Path, args: tuple[str, ...]):
    # Repository config is executable input (hooks, filters, fsmonitor). Never
    # inherit user/system configuration or GIT_* environment into control actions.
    env = {
        "PATH": os.defpath,
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "en_US.UTF-8",
    }
    prefix = [
        "git",
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "core.fsmonitor=false",
        "-c",
        "submodule.recurse=false",
        "-c",
        "protocol.file.allow=never",
        "-c",
        "core.attributesFile=" + os.devnull,
    ]
    config = subprocess.run(
        prefix + ["config", "--local", "--no-includes", "-z", "--list"],
        cwd=repo,
        env=env,
        capture_output=True,
        timeout=15,
    )
    if config.returncode:
        raise ValueError("Unreadable repository configuration")
    for entry in config.stdout.split(b"\0"):
        key = entry.split(b"\n", 1)[0].decode(errors="replace").lower()
        if key.startswith(("filter.", "include.", "includeif.")):
            raise ValueError(
                "Executable or included Git configuration requires qualification"
            )
    return subprocess.run(
        prefix + list(args), cwd=repo, env=env, capture_output=True, timeout=30
    )


def git(repo: Path, *args: str) -> str:
    result = _git_run(repo, args)
    if result.returncode:
        raise ValueError("Git operation failed: " + " ".join(args[:2]))
    return result.stdout.decode().strip()


def files(repo: Path) -> list[str]:
    result = _git_run(
        repo, ("ls-files", "-z", "--cached", "--others", "--exclude-standard")
    )
    if result.returncode:
        raise ValueError("Cannot enumerate candidate files")
    return sorted(set(os.fsdecode(x) for x in result.stdout.split(b"\0") if x))


def _read_regular(repo: Path, relative: Path) -> tuple[bytes, bool]:
    fd = os.open(repo, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in relative.parts[:-1]:
            child = os.open(
                part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
            )
            os.close(fd)
            fd = child
        file_fd = os.open(relative.name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=fd)
        try:
            info = os.fstat(file_fd)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_size > 20_000_000
            ):
                raise ValueError(
                    "Candidate file requires a larger qualified resource limit"
                )
            with os.fdopen(file_fd, "rb", closefd=False) as handle:
                data = handle.read(20_000_001)
            if len(data) > 20_000_000:
                raise ValueError("Candidate file exceeded resource limit")
            return data, bool(info.st_mode & 0o111)
        finally:
            os.close(file_fd)
    finally:
        os.close(fd)


def content_manifest(repo: Path) -> dict:
    repo = repo.resolve(strict=True)
    entries = {}
    for name in files(repo):
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe tracked path")
        path = repo / relative
        if any(p.is_symlink() for p in (path, *path.parents) if p != repo.parent):
            raise ValueError(
                "Candidate symlinks require a separately qualified adapter"
            )
        if not path.exists():
            entries[name] = {"deleted": True}
            continue
        if not path.is_file():
            raise ValueError("Unsupported candidate path")
        if relative.name == ".env" or relative.name.startswith(".env."):
            if relative.suffix not in {".example", ".sample", ".template"}:
                raise ValueError("Credential files cannot enter a candidate")
        data, executable = _read_regular(repo, relative)
        entries[name] = {
            "sha256": hashlib.sha256(data).hexdigest(),
            "executable": executable,
        }
    obj = {"head": git(repo, "rev-parse", "HEAD"), "files": entries}
    obj["digest"] = digest_json(obj)
    return obj


def snapshot(repo: Path, destination: Path) -> dict:
    manifest = content_manifest(repo)
    destination.mkdir(parents=True, exist_ok=False)
    for name, entry in manifest["files"].items():
        if entry.get("deleted"):
            continue
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        data, executable = _read_regular(repo, Path(name))
        if (
            hashlib.sha256(data).hexdigest() != entry["sha256"]
            or executable != entry["executable"]
        ):
            raise ValueError("Candidate changed during snapshot")
        target.write_bytes(data)
        target.chmod(0o555 if entry["executable"] else 0o444)
    # No Git administrative paths or shared refs are copied into a test candidate.
    manifest["path"] = str(destination.resolve())
    # Give Codex a real repository boundary so instruction discovery does not
    # traverse unrelated control/host directories. No shared Git refs or hooks.
    subprocess.run(
        ["git", "init", "--template=", "-b", "candidate", str(destination)],
        env={
            "PATH": os.defpath,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        },
        capture_output=True,
        check=True,
        timeout=15,
    )
    write_json(destination.parent / (destination.name + ".json"), manifest)
    return manifest


def verify_snapshot(manifest: dict) -> bool:
    if (
        digest_json({"head": manifest["head"], "files": manifest["files"]})
        != manifest["digest"]
    ):
        return False
    root = Path(manifest["path"])
    expected = {n for n, e in manifest["files"].items() if not e.get("deleted")}
    actual = {
        p.relative_to(root).as_posix()
        for p in root.rglob("*")
        if (p.is_file() or p.is_symlink()) and ".git" not in p.relative_to(root).parts
    }
    if expected != actual:
        return False
    for name in expected:
        p = root / name
        if (
            p.is_symlink()
            or hashlib.sha256(p.read_bytes()).hexdigest()
            != manifest["files"][name]["sha256"]
            or bool(p.stat().st_mode & 0o111) != manifest["files"][name]["executable"]
        ):
            return False
    return True


def worktree(repo: Path, directory: Path, job_id: str) -> dict:
    if git(repo, "status", "--porcelain"):
        raise ValueError(
            "Start jobs from a clean committed base; existing user edits are preserved"
        )
    if Path(git(repo, "rev-parse", "--show-toplevel")).resolve() != repo.resolve():
        raise ValueError("A repository root is required")
    branch = "cep/" + job_id
    base = git(repo, "rev-parse", "HEAD")
    directory.parent.mkdir(parents=True, exist_ok=True)
    git(repo, "worktree", "add", "-b", branch, str(directory), base)
    return {
        "path": str(directory.resolve()),
        "branch": branch,
        "base_sha": base,
        "repository": str(repo.resolve()),
    }
