"""Versioned, declarative technology packs. Loading a pack never runs commands."""

from __future__ import annotations

import fnmatch
import json
from pathlib import Path
import re

from .project import (
    ProjectError,
    discover_files,
    project_root,
    relative_path,
    safe_path,
)


class PackError(ValueError):
    """A pack is malformed or requests an unsupported action."""


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+(?:-[a-zA-Z0-9.-]+)?$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9_.:-]{0,127}$")


def _object(
    value: object, fields: set[str], label: str, *, required: set[str] | None = None
) -> dict:
    if not isinstance(value, dict):
        raise PackError(f"{label} must be an object")
    unknown = value.keys() - fields
    missing = (required if required is not None else fields) - value.keys()
    if unknown or missing:
        raise PackError(
            f"{label}: unknown fields {sorted(unknown)}, missing fields {sorted(missing)}"
        )
    return value


def _strings(value: object, label: str, *, nonempty: bool = False) -> list[str]:
    if not isinstance(value, list) or not all(
        isinstance(v, str) and v and not any(ord(c) < 32 for c in v) for v in value
    ):
        raise PackError(f"{label} must be an array of nonempty strings")
    if nonempty and not value:
        raise PackError(f"{label} must not be empty")
    if len(set(value)) != len(value):
        raise PackError(f"{label} contains duplicates")
    return value


def _pairs(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PackError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_pack(path: Path) -> dict:
    """Read one v1 pack directory or manifest and reject nondeclarative fields.

    Commands are argv data, not trusted or approved execution. Pack conformance
    does not confer filesystem, network, provider, or deployment authorization.
    """
    path = Path(path).absolute()
    if path.is_symlink():
        raise PackError("pack root/manifest must not be a symlink")
    if path.is_dir():
        path = safe_path(path.resolve(), "pack.json")
    if not path.is_file() or path.stat().st_size > 1_048_576:
        raise PackError("pack manifest must be a regular file below 1 MiB")
    try:
        data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_pairs)
        _object(
            data,
            {
                "schema_version",
                "id",
                "version",
                "description",
                "detect",
                "toolchains",
                "commands",
                "roles",
                "required_capabilities",
            },
            "pack",
        )
        if type(data["schema_version"]) is not int or data["schema_version"] != 1:
            raise PackError("unsupported pack schema_version")
        if not isinstance(data["id"], str) or not _IDENTIFIER.fullmatch(data["id"]):
            raise PackError("invalid pack id")
        if not isinstance(data["version"], str) or not _VERSION.fullmatch(
            data["version"]
        ):
            raise PackError("version must be a semantic x.y.z version")
        if not isinstance(data["description"], str) or not data["description"].strip():
            raise PackError("description must not be empty")
        detect = _object(data["detect"], {"any_files"}, "detect")
        for pattern in _strings(detect["any_files"], "detect.any_files", nonempty=True):
            relative_path(pattern, pattern=True)
            if pattern == "." or pattern.startswith(".git/"):
                raise PackError("detection must name project files")
        if not isinstance(data["toolchains"], list) or not data["toolchains"]:
            raise PackError("toolchains must be a nonempty array")
        tool_ids = set()
        for tool in data["toolchains"]:
            _object(
                tool, {"name", "version_command", "version_constraint"}, "toolchain"
            )
            if not isinstance(tool["name"], str) or not _IDENTIFIER.fullmatch(
                tool["name"]
            ):
                raise PackError("invalid toolchain name")
            if tool["name"] in tool_ids:
                raise PackError("duplicate toolchain name")
            tool_ids.add(tool["name"])
            _argv(tool["version_command"], "version_command")
            if (
                not isinstance(tool["version_constraint"], str)
                or not tool["version_constraint"]
            ):
                raise PackError("toolchain version_constraint is required")
        if not isinstance(data["commands"], list) or not data["commands"]:
            raise PackError("commands must be a nonempty array")
        command_ids = set()
        for command in data["commands"]:
            _object(
                command,
                {"id", "action", "argv", "cwd", "timeout_seconds", "required"},
                "command",
            )
            if not isinstance(command["id"], str) or not _IDENTIFIER.fullmatch(
                command["id"]
            ):
                raise PackError("invalid command id")
            if command["id"] in command_ids:
                raise PackError("duplicate command id")
            command_ids.add(command["id"])
            if command["action"] not in {
                "test",
                "lint",
                "typecheck",
                "build",
                "security",
                "format-check",
            }:
                raise PackError(
                    "unsupported action; deployment/setup hooks are not pack actions"
                )
            _argv(command["argv"], "command.argv")
            relative_path(command["cwd"])
            if (
                type(command["timeout_seconds"]) is not int
                or not 1 <= command["timeout_seconds"] <= 3600
            ):
                raise PackError("timeout_seconds must be 1..3600")
            if type(command["required"]) is not bool:
                raise PackError("required must be a boolean")
        for role in _strings(data["roles"], "roles"):
            if not _IDENTIFIER.fullmatch(role):
                raise PackError("invalid role identifier")
        for capability in _strings(
            data["required_capabilities"], "required_capabilities"
        ):
            if not _CAPABILITY.fullmatch(capability):
                raise PackError("invalid capability identifier")
    except (ProjectError, TypeError, UnicodeError, json.JSONDecodeError) as exc:
        raise PackError(str(exc)) from exc
    return data


def _argv(value: object, label: str) -> None:
    # Repeated args can be meaningful, unlike identifiers, so don't deduplicate.
    if (
        not isinstance(value, list)
        or not value
        or not all(
            isinstance(v, str) and v and not any(ord(c) < 32 for c in v) for v in value
        )
    ):
        raise PackError(f"{label} must be a nonempty argv array")
    exe = value[0]
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.+-]*", exe):
        raise PackError(
            "executables must be tool names resolved in the qualified environment"
        )
    if exe in {"sh", "bash", "zsh", "fish", "cmd", "powershell", "pwsh", "sudo", "env"}:
        raise PackError(
            "shell and privilege wrappers are not supported pack executables"
        )
    # Args are never interpolated, but explicit escapes to another root are errors.
    for arg in value[1:]:
        if arg.startswith(("/", "~/")) or "\\" in arg or ".." in arg.split("/"):
            raise PackError("command arguments must not reference outside paths")


def discover_packs(root: Path, project: Path) -> list[dict]:
    """Load external packs, report matches; do not activate or execute them."""
    root = project_root(root)
    project = project_root(project)
    files, _ = discover_files(project)
    candidates = [root] if (root / "pack.json").exists() else sorted(root.iterdir())
    results = []
    seen = set()
    for candidate in candidates:
        if candidate.is_symlink():
            raise PackError("symlinked pack entries are not supported")
        if not candidate.is_dir() or not (candidate / "pack.json").exists():
            continue
        pack = load_pack(candidate)
        if pack["id"] in seen:
            raise PackError(f"duplicate pack id: {pack['id']}")
        seen.add(pack["id"])
        matches = sorted(
            {
                p
                for p in files
                for pattern in pack["detect"]["any_files"]
                if fnmatch.fnmatchcase(p, pattern)
                or fnmatch.fnmatchcase(Path(p).name, pattern)
            }
        )
        results.append(
            {
                **pack,
                "path": str(candidate),
                "matches": matches,
                "detected": bool(matches),
                "activated": False,
            }
        )
    return results
