"""Selective project integration with dry runs, ownership and crash journals.

This installer is not the execution security boundary. Its state is local,
ignored project metadata. It never edits global Codex configuration, follows
descendant symlinks, executes bundled code, or overwrites unowned content.
"""

from __future__ import annotations

import base64
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib
import uuid

from .packs import discover_packs
from .project import (
    inspect_project,
    project_root,
    read_project_manifest,
    relative_path,
    safe_path,
)


class InstallError(ValueError):
    """An install cannot proceed without risking existing user content."""


_STATE = ".cep/install-state.json"
_PLUGIN_KEY = "codex-engineering-platform@codex-engineering-platform"
_BASE_ROLES = [
    "code_reviewer",
    "test_designer",
    "documentation_engineer",
    "learning_curator",
]
_ROLE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def _digest(data: bytes | None) -> str | None:
    return hashlib.sha256(data).hexdigest() if data is not None else None


def _encoded(data: bytes | None) -> str | None:
    return base64.b64encode(data).decode("ascii") if data is not None else None


def _decoded(data: str | None) -> bytes | None:
    if data is None:
        return None
    if not isinstance(data, str):
        raise InstallError("invalid installation snapshot")
    try:
        return base64.b64decode(data, validate=True)
    except ValueError as exc:
        raise InstallError("invalid installation snapshot") from exc


def _managed_path(path: str) -> str:
    path = relative_path(path)
    if path in {"engineering-platform.toml", ".gitignore", ".codex/config.toml"}:
        return path
    if (
        path.startswith(".codex/agents/")
        and _ROLE.fullmatch(Path(path).stem)
        and path == f".codex/agents/{Path(path).stem}.toml"
    ):
        return path
    raise InstallError(f"installer cannot manage this path: {path}")


class _Tree:
    """Operate relative to directory descriptors to prevent symlink traversal."""

    def __init__(self, root: Path):
        self.root = root
        self.fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)

    def close(self) -> None:
        os.close(self.fd)

    @contextmanager
    def parent(self, relative: str, *, create: bool = False):
        parts = Path(relative_path(relative)).parts
        fd = os.dup(self.fd)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, mode=0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                next_fd = os.open(
                    part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd
                )
                os.close(fd)
                fd = next_fd
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def read(self, relative: str) -> bytes | None:
        try:
            with self.parent(relative) as (parent, name):
                fd = os.open(
                    name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent
                )
                try:
                    info = os.fstat(fd)
                    if (
                        not stat.S_ISREG(info.st_mode)
                        or info.st_size > 16 * 1024 * 1024
                    ):
                        raise InstallError(f"not a supported regular file: {relative}")
                    with os.fdopen(os.dup(fd), "rb") as stream:
                        return stream.read(16 * 1024 * 1024 + 1)
                finally:
                    os.close(fd)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise InstallError(f"unsafe or inaccessible path: {relative}") from exc

    def write(self, relative: str, data: bytes) -> None:
        try:
            with self.parent(relative, create=True) as (parent, name):
                temp = f".cep-{uuid.uuid4().hex}.tmp"
                fd = os.open(
                    temp,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                    0o600,
                    dir_fd=parent,
                )
                try:
                    with os.fdopen(fd, "wb") as stream:
                        stream.write(data)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, name, src_dir_fd=parent, dst_dir_fd=parent)
                    os.fsync(parent)
                finally:
                    try:
                        os.unlink(temp, dir_fd=parent)
                    except FileNotFoundError:
                        pass
        except OSError as exc:
            raise InstallError(f"cannot safely write: {relative}") from exc

    def delete(self, relative: str) -> None:
        try:
            with self.parent(relative) as (parent, name):
                os.unlink(name, dir_fd=parent)
                os.fsync(parent)
        except FileNotFoundError:
            pass

    @contextmanager
    def lock(self):
        with self.parent(".cep/install.lock", create=True) as (parent, name):
            try:
                fd = os.open(
                    name, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600, dir_fd=parent
                )
            except OSError as exc:
                raise InstallError("cannot open a safe installation lock") from exc
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise InstallError("installation lock must be a regular file")
                try:
                    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise InstallError(
                        "another installer is active for this project"
                    ) from exc
                # Keep private rollback snapshots ignored even if a crash occurs
                # after restoring the project's original top-level .gitignore.
                local_ignore = self.read(".cep/.gitignore")
                if local_ignore is None:
                    self.write(".cep/.gitignore", b"*\n")
                elif local_ignore.rstrip().splitlines()[-1:] != [b"*"]:
                    raise InstallError(
                        "existing .cep/.gitignore does not protect private state; preserve and reconcile it"
                    )
                yield
            finally:
                os.close(fd)


def _load_state(tree: _Tree) -> dict:
    raw = tree.read(_STATE)
    if raw is None:
        return {"schema_version": 1, "files": {}, "history": []}
    try:
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise InstallError("installation state must be an object")
        if type(state.get("schema_version")) is not int or state["schema_version"] != 1:
            raise InstallError("unsupported installation state version")
        if not isinstance(state["files"], dict) or not isinstance(
            state["history"], list
        ):
            raise InstallError("invalid installation ownership state")
        _validate_files(state["files"])
        for item in state["history"] + (
            [state["pending"]] if state.get("pending") else []
        ):
            _validate_files(item["files_before"])
            if not isinstance(item["changes"], list):
                raise InstallError("invalid installation transaction")
            paths = set()
            for change in item["changes"]:
                path = _managed_path(change["path"])
                if path in paths:
                    raise InstallError("duplicate transaction path")
                paths.add(path)
                _decoded(change["before"])
                _decoded(change["after"])
        return state
    except (KeyError, TypeError, ValueError, UnicodeError) as exc:
        raise InstallError(f"invalid installation state: {exc}") from exc


def _validate_files(files: dict) -> None:
    if not isinstance(files, dict):
        raise InstallError("invalid managed file records")
    for path, record in files.items():
        _managed_path(path)
        if not isinstance(record, dict) or not re.fullmatch(
            r"[a-f0-9]{64}", str(record.get("sha256", ""))
        ):
            raise InstallError("invalid managed file digest")
        _decoded(record["original"])


def _save_state(tree: _Tree, state: dict) -> None:
    if not state["files"] and not state["history"] and not state.get("pending"):
        tree.delete(_STATE)
    else:
        tree.write(
            _STATE, (json.dumps(state, indent=2, sort_keys=True) + "\n").encode()
        )


def _plugin_root(bundle: Path) -> Path:
    root = project_root(bundle)
    if (root / "plugin.json").exists():
        return root
    return project_root(safe_path(root, "plugin"))


def _desired(
    project: Path, bundle: Path, tree: _Tree
) -> tuple[dict[str, bytes], list[str], list[str]]:
    plugin = _plugin_root(bundle)
    info = inspect_project(project)
    existing = read_project_manifest(project)
    warnings = list(info["warnings"])
    pack_root = safe_path(plugin, "packs")
    packs = discover_packs(pack_root, project) if pack_root.is_dir() else []
    for relative in existing.get("pack_paths", []) if existing else []:
        packs.extend(discover_packs(safe_path(project, relative), project))
    pack_ids = [pack["id"] for pack in packs]
    if len(set(pack_ids)) != len(pack_ids):
        raise InstallError("duplicate pack IDs across bundled and project catalogs")
    # Packs are suggestions until explicitly selected in a project manifest.
    selected = existing.get("packs", []) if existing else []
    roles = list(existing.get("roles", _BASE_ROLES)) if existing else list(_BASE_ROLES)
    for pack in packs:
        if pack["id"] in selected:
            roles.extend(pack["roles"])
    unavailable = sorted(set(selected) - {p["id"] for p in packs})
    if unavailable:
        raise InstallError(
            f"selected packs are not available in this bundle: {', '.join(unavailable)}"
        )
    roles = sorted(set(roles))
    role_sources = {}
    for pack in packs:
        if pack["id"] not in selected:
            continue
        for role in pack["roles"]:
            asset = safe_path(Path(pack["path"]), f"agents/{role}.toml")
            if asset.is_file():
                previous = role_sources.get(role)
                if previous and previous.read_bytes() != asset.read_bytes():
                    raise InstallError(
                        f"selected packs disagree on agent profile: {role}"
                    )
                role_sources[role] = asset
    desired: dict[str, bytes] = {}
    if existing is None:
        template = safe_path(plugin, "assets/engineering-platform.toml")
        if not template.is_file():
            raise InstallError("bundle lacks project manifest template")
        text = template.read_text(encoding="utf-8")
        text = text.replace("__PROJECT_NAME_JSON__", json.dumps(project.name))
        text = text.replace("__REPOSITORIES_JSON__", json.dumps(info["repositories"]))
        desired["engineering-platform.toml"] = text.encode()
    else:
        desired["engineering-platform.toml"] = tree.read("engineering-platform.toml")
    for role in roles:
        if not _ROLE.fullmatch(role):
            raise InstallError(f"invalid agent role: {role!r}")
        source = safe_path(plugin, f"assets/agents/{role}.toml")
        external = role_sources.get(role)
        if external:
            if source.is_file() and source.read_bytes() != external.read_bytes():
                raise InstallError(
                    f"pack tries to override a bundled agent profile: {role}"
                )
            source = external
        if not source.is_file():
            raise InstallError(f"selected agent profile is unavailable: {role}")
        raw = source.read_bytes()
        profile = tomllib.loads(raw.decode())
        if profile.get("name") != role or not all(
            profile.get(k) for k in ("description", "developer_instructions")
        ):
            raise InstallError(f"invalid agent profile: {role}")
        if any(
            k in profile
            for k in (
                "sandbox_mode",
                "approval_policy",
                "mcp_servers",
                "model_provider",
            )
        ):
            raise InstallError(
                f"agent profile claims unsupported permission overrides: {role}"
            )
        desired[f".codex/agents/{role}.toml"] = raw
    old_config = tree.read(".codex/config.toml") or b""
    try:
        config = tomllib.loads(old_config.decode())
    except (UnicodeError, ValueError) as exc:
        raise InstallError("existing Codex configuration is not valid TOML") from exc
    if not isinstance(config.get("plugins", {}), dict):
        raise InstallError("existing Codex plugins setting must be a TOML table")
    setting = config.get("plugins", {}).get(_PLUGIN_KEY)
    if setting is not None:
        if not isinstance(setting, dict) or setting.get("enabled") is not True:
            raise InstallError(
                "project explicitly disables or conflicts with this plugin; preserve the setting"
            )
        desired[".codex/config.toml"] = old_config
    else:
        desired[".codex/config.toml"] = (
            old_config
            + (b"\n" if old_config and not old_config.endswith(b"\n") else b"")
            + (
                f'\n# Codex Engineering Platform project activation\n[plugins."{_PLUGIN_KEY}"]\nenabled = true\n'
            ).encode()
        )
    ignore = tree.read(".gitignore") or b""
    # The final pattern must ignore receipts even if an earlier user rule used
    # a later negation. Merely finding an ignore anywhere is not sufficient.
    if not ignore.rstrip().endswith(b"/.cep/"):
        ignore += (
            b"\n" if ignore and not ignore.endswith(b"\n") else b""
        ) + b"\n# Local CEP installation receipts and private snapshots\n/.cep/\n"
    desired[".gitignore"] = ignore
    if not selected:
        warnings.append(
            "technology packs are detected but not activated; select pack ids in engineering-platform.toml after review"
        )
    if info["ownership"]:
        warnings.append(
            "existing workspace tooling owns project-specific setup; reconcile through that tooling before applying"
        )
    return desired, roles, warnings


def _plan(
    tree: _Tree, desired: dict[str, bytes], state: dict
) -> tuple[list[dict], dict, list[str], list[str]]:
    changes = []
    owned = dict(state["files"])
    conflicts = []
    preserved = []
    for path, wanted in desired.items():
        path = _managed_path(path)
        current = tree.read(path)
        record = owned.get(path)
        if current == wanted:
            continue
        if record and _digest(current) != record["sha256"]:
            conflicts.append(path)
            continue
        if (
            current is not None
            and not record
            and path not in {".codex/config.toml", ".gitignore"}
        ):
            conflicts.append(path)
            continue
        changes.append(
            {"path": path, "before": _encoded(current), "after": _encoded(wanted)}
        )
        owned[path] = {
            "sha256": _digest(wanted),
            "original": record["original"] if record else _encoded(current),
        }
    for path in sorted(set(owned) - desired.keys()):
        current = tree.read(path)
        record = owned[path]
        if _digest(current) != record["sha256"]:
            preserved.append(path)
            continue
        before = _decoded(record["original"])
        changes.append(
            {"path": path, "before": _encoded(current), "after": _encoded(before)}
        )
        del owned[path]
    return changes, owned, conflicts, preserved


def _commit(
    tree: _Tree, state: dict, changes: list[dict], files: dict, history: list[dict]
) -> None:
    # Store undo data durably before changing any managed file. On interruption,
    # ordinary installs fail closed; rollback reconciles before/after digests.
    journal = {"files_before": state["files"], "changes": changes}
    _save_state(tree, {**state, "pending": journal})
    for change in changes:
        if tree.read(change["path"]) != _decoded(change["before"]):
            raise InstallError(
                f"file changed during installation: {change['path']}; use rollback"
            )
        data = _decoded(change["after"])
        if data is None:
            tree.delete(change["path"])
        else:
            tree.write(change["path"], data)
    _save_state(tree, {"schema_version": 1, "files": files, "history": history})


def install_project(project: Path, bundle: Path, apply: bool = False) -> dict:
    """Plan or selectively install/update project files. No global writes."""
    root = project_root(project)
    tree = _Tree(root)
    try:

        def operation() -> dict:
            state = _load_state(tree)
            if state.get("pending"):
                raise InstallError(
                    "interrupted installation found; run rollback before continuing"
                )
            desired, roles, warnings = _desired(root, bundle, tree)
            changes, files, conflicts, preserved = _plan(tree, desired, state)
            result = {
                "operation": "install",
                "applied": False,
                "status": "conflict" if conflicts else "planned",
                "changes": [
                    {
                        "path": c["path"],
                        "action": "remove"
                        if c["after"] is None
                        else "create"
                        if c["before"] is None
                        else "update",
                    }
                    for c in changes
                ],
                "conflicts": conflicts,
                "preserved": preserved,
                "roles": roles,
                "warnings": warnings,
            }
            if apply and not conflicts:
                if changes:
                    journal = {"files_before": state["files"], "changes": changes}
                    _commit(
                        tree,
                        state,
                        changes,
                        files,
                        (state["history"] + [journal])[-20:],
                    )
                result.update(
                    applied=True, status="installed" if changes else "unchanged"
                )
            return result

        # Preflight before creating even a lock directory, then repeat under lock.
        preview = operation() if not apply else None
        if preview is not None:
            return preview
        state = _load_state(tree)
        desired, _, _ = _desired(root, bundle, tree)
        _, _, conflicts, _ = _plan(tree, desired, state)
        if conflicts:
            apply = False
            return operation()
        with tree.lock():
            return operation()
    finally:
        tree.close()


def rollback_project(project: Path, apply: bool = False) -> dict:
    """Undo the last transaction, or reconcile a partially applied transaction."""
    tree = _Tree(project_root(project))
    try:

        def operation() -> dict:
            state = _load_state(tree)
            interrupted = bool(state.get("pending"))
            journal = state.get("pending") or (
                state["history"][-1] if state["history"] else None
            )
            if not journal:
                return {
                    "operation": "rollback",
                    "applied": False,
                    "status": "unchanged",
                    "changes": [],
                    "conflicts": [],
                }
            conflicts = []
            changes = []
            for change in reversed(journal["changes"]):
                current = tree.read(change["path"])
                before, after = _decoded(change["before"]), _decoded(change["after"])
                if interrupted and current == before:
                    continue
                if current != after:
                    conflicts.append(change["path"])
                else:
                    changes.append(
                        {
                            "path": change["path"],
                            "before": _encoded(current),
                            "after": _encoded(before),
                        }
                    )
            result = {
                "operation": "rollback",
                "applied": False,
                "status": "conflict" if conflicts else "planned",
                "changes": [c["path"] for c in changes],
                "conflicts": conflicts,
            }
            if apply and not conflicts:
                history = state["history"] if interrupted else state["history"][:-1]
                if interrupted:
                    # Existing journal is sufficient for idempotent recovery.
                    for change in changes:
                        if tree.read(change["path"]) != _decoded(change["before"]):
                            raise InstallError(
                                f"file changed during rollback: {change['path']}"
                            )
                        data = _decoded(change["after"])
                        if data is None:
                            tree.delete(change["path"])
                        else:
                            tree.write(change["path"], data)
                    _save_state(
                        tree,
                        {
                            "schema_version": 1,
                            "files": journal["files_before"],
                            "history": history,
                        },
                    )
                else:
                    _commit(tree, state, changes, journal["files_before"], history)
                result.update(applied=True, status="rolled_back")
            return result

        if apply:
            state = _load_state(tree)
            if not state["history"] and not state.get("pending"):
                return operation()
            with tree.lock():
                return operation()
        return operation()
    finally:
        tree.close()


def uninstall_project(project: Path, apply: bool = False) -> dict:
    """Restore owned originals; preserve changed files and their ownership record."""
    tree = _Tree(project_root(project))
    try:

        def operation() -> dict:
            state = _load_state(tree)
            if state.get("pending"):
                raise InstallError("interrupted installation found; run rollback first")
            changes, preserved, remaining = [], [], {}
            for path, record in state["files"].items():
                current = tree.read(path)
                if _digest(current) != record["sha256"]:
                    preserved.append(path)
                    remaining[path] = record
                else:
                    changes.append(
                        {
                            "path": path,
                            "before": _encoded(current),
                            "after": record["original"],
                        }
                    )
            # Keep receipts ignored while changed managed files still need review.
            if remaining:
                changes = [c for c in changes if c["path"] != ".gitignore"]
                if ".gitignore" in state["files"]:
                    remaining[".gitignore"] = state["files"][".gitignore"]
            result = {
                "operation": "uninstall",
                "applied": False,
                "status": "planned",
                "changes": [c["path"] for c in changes],
                "preserved": sorted(preserved),
                "conflicts": [],
            }
            if apply:
                if changes:
                    _commit(tree, state, changes, remaining, [])
                result.update(
                    applied=True,
                    status="preserved_edits" if preserved else "uninstalled",
                )
            return result

        if apply:
            state = _load_state(tree)
            if not state["files"] and not state.get("pending"):
                return operation()
            with tree.lock():
                return operation()
        return operation()
    finally:
        tree.close()
