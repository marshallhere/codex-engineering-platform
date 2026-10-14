"""Read-only, bounded project discovery. Discovery never executes project code."""

from __future__ import annotations

import os
from itertools import islice
from pathlib import Path, PurePosixPath
import tomllib


class ProjectError(ValueError):
    """A project configuration or filesystem boundary is invalid."""


def relative_path(value: str, *, pattern: bool = False) -> str:
    """Validate portable paths before joining them to an explicit root."""
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise ProjectError("expected a nonempty portable relative path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or ":" in value:
        raise ProjectError(f"path must stay beneath its root: {value!r}")
    if any(ord(c) < 32 for c in value):
        raise ProjectError("control characters are not allowed in paths")
    if not pattern and any(c in value for c in "*?["):
        raise ProjectError("wildcards are only allowed in detection patterns")
    return path.as_posix()


def project_root(path: Path) -> Path:
    path = Path(path).absolute()
    if path.is_symlink():
        raise ProjectError("project root must not be a symbolic link")
    root = path.resolve(strict=True)
    if not root.is_dir():
        raise ProjectError("project root must be a directory")
    return root


def safe_path(root: Path, relative: str) -> Path:
    """Reject symlinks, including dangling links, at every descendant component."""
    clean = relative_path(relative)
    current = root
    for part in PurePosixPath(clean).parts:
        current = current / part
        if current.is_symlink():
            raise ProjectError(f"symbolic links are not followed: {relative}")
    if not current.resolve().is_relative_to(root):
        raise ProjectError("path escaped project root")
    return current


def read_project_manifest(root: Path) -> dict | None:
    path = safe_path(root, "engineering-platform.toml")
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > 1_048_576:
        raise ProjectError("project manifest must be a regular file below 1 MiB")
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except (ValueError, UnicodeError) as exc:
        raise ProjectError(f"invalid project manifest: {exc}") from exc
    if type(data.get("schema_version")) is not int or data["schema_version"] != 1:
        raise ProjectError("unsupported project manifest schema_version")
    allowed = {
        "schema_version",
        "name",
        "repositories",
        "packs",
        "pack_paths",
        "roles",
        "autonomy",
    }
    if data.keys() - allowed:
        raise ProjectError(
            f"unknown project manifest fields: {', '.join(sorted(data.keys() - allowed))}"
        )
    if "name" in data and (
        not isinstance(data["name"], str) or not data["name"].strip()
    ):
        raise ProjectError("project name must be a nonempty string")
    autonomy = data.get("autonomy", {})
    if not isinstance(autonomy, dict) or autonomy.keys() - {"auto_merge"}:
        raise ProjectError(
            "autonomy supports only the project auto_merge preference; grants belong to runtime policy"
        )
    if "auto_merge" in autonomy and type(autonomy["auto_merge"]) is not bool:
        raise ProjectError("autonomy.auto_merge must be a boolean")
    for key in ("repositories", "packs", "pack_paths", "roles"):
        values = data.get(key, [])
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ProjectError(f"{key} must be an array of strings")
    for value in data.get("repositories", ["."]):
        safe_path(root, value)
    for value in data.get("pack_paths", []):
        safe_path(root, value)
    for key in ("packs", "roles"):
        for value in data.get(key, []):
            if not value or any(
                c not in "abcdefghijklmnopqrstuvwxyz0123456789_-" for c in value
            ):
                raise ProjectError(f"invalid {key} identifier: {value!r}")
    return data


_MARKERS = {
    "pyproject.toml": "python",
    "requirements.txt": "python",
    "setup.py": "python",
    "go.mod": "go",
    "package.json": "javascript",
    "pom.xml": "java",
    "build.gradle": "java",
    "build.gradle.kts": "java",
    "Cargo.toml": "rust",
    "docker-compose.yml": "compose",
    "docker-compose.dev.yml": "compose",
    "compose.yaml": "compose",
    "compose.yml": "compose",
}
_SKIP = {
    ".git",
    ".cep",
    ".venv",
    "venv",
    "node_modules",
    ".next",
    "__pycache__",
    "target",
    "vendor",
}


def discover_files(
    root: Path, *, max_depth: int = 4, max_entries: int = 20_000
) -> tuple[list[str], list[str]]:
    """Enumerate filenames without following links or opening their contents."""
    files: list[str] = []
    warnings: list[str] = []
    remaining = max_entries
    queue = [(root, 0)]
    while queue and remaining:
        directory, depth = queue.pop()
        try:
            with os.scandir(directory) as entries:
                for entry in sorted(islice(entries, remaining), key=lambda e: e.name):
                    remaining -= 1
                    rel = Path(entry.path).relative_to(root).as_posix()
                    if entry.is_symlink():
                        warnings.append(f"ignored symlink: {rel}")
                    elif entry.is_file(follow_symlinks=False):
                        files.append(rel)
                    elif (
                        entry.is_dir(follow_symlinks=False) and entry.name not in _SKIP
                    ):
                        if depth < max_depth:
                            queue.append((Path(entry.path), depth + 1))
                    if not remaining:
                        warnings.append(
                            "discovery entry limit reached; inspect deeper paths explicitly"
                        )
                        break
        except OSError as exc:
            warnings.append(
                f"cannot inspect {directory.relative_to(root)}: {exc.strerror}"
            )
    return sorted(files), warnings


def inspect_project(project: Path) -> dict:
    """Return facts and hints, never inferred permission or executable commands."""
    root = project_root(project)
    manifest = read_project_manifest(root)
    files, warnings = discover_files(root)
    file_set = set(files)
    repos = {"."} if (root / ".git").exists() else set()
    for entry in sorted(islice(root.iterdir(), 20_000)):
        if entry.is_dir() and not entry.is_symlink() and entry.name not in _SKIP:
            git = entry / ".git"
            if git.exists() and not git.is_symlink():
                repos.add(entry.name)
    if manifest:
        for rel in manifest.get("repositories", []):
            location = safe_path(root, rel)
            if not location.is_dir():
                warnings.append(f"configured repository is missing: {rel}")
            else:
                repos.add(relative_path(rel))
    markers = [
        {"path": p, "technology": _MARKERS[Path(p).name]}
        for p in files
        if Path(p).name in _MARKERS
    ]
    instructions = [
        p for p in files if Path(p).name in {"AGENTS.md", "AGENTS.override.md"}
    ]
    hints = sorted({m["technology"] for m in markers})
    ownership = []
    if "eventu-tooling/bin/eventu" in file_set:
        ownership.append(
            {
                "path": "eventu-tooling",
                "kind": "existing-project-tooling",
                "action": "preserve",
            }
        )
    return {
        "schema_version": 1,
        "root": str(root),
        "name": root.name,
        "repositories": sorted(repos) or ["."],
        "multi_repo": len(repos) > 1,
        "markers": markers,
        "instructions": instructions,
        "technology_hints": hints,
        "project_manifest": manifest,
        "ownership": ownership,
        "warnings": warnings,
        "commands_executed": [],
    }
