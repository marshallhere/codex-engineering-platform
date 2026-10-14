"""Inventory capability metadata without exporting machine bindings or secrets.

Only explicit Codex config files, skill entrypoints, plugin manifests and license
markers are read. Auth stores, environment files, sessions and private memory are
never inputs. An inventory is not a provider connectivity or delivery test.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import stat
import tomllib
from urllib.parse import urlsplit


_NAME = re.compile(r"^[A-Za-z][A-Za-z0-9_.:-]{0,79}$")
_ENV = re.compile(r"^[A-Z][A-Z0-9_]{0,127}$")
_VERSION = re.compile(r"^[0-9]+(?:\.[0-9A-Za-z_-]+)*(?:[-+][0-9A-Za-z_.-]+)?$")
_PUBLIC_ENDPOINTS = {
    ("mcp.stripe.com", ""),
    ("mcp.stripe.com", "/"),
    ("developers.openai.com", "/mcp"),
    ("mcp.context7.com", "/mcp"),
    ("api.githubcopilot.com", "/mcp/"),
    ("api.githubcopilot.com", "/mcp"),
    ("mcp.resend.com", ""),
    ("mcp.resend.com", "/"),
}
_EXECUTABLES = {
    "npx",
    "node",
    "nodejs",
    "uvx",
    "uv",
    "python",
    "python3",
    "docker",
    "go",
    "java",
    "codex",
}
_LICENSES = {
    "MIT",
    "Apache-2.0",
    "BSD-2-Clause",
    "BSD-3-Clause",
    "ISC",
    "MPL-2.0",
    "GPL-3.0-only",
    "AGPL-3.0-only",
    "proprietary",
}
_DENIED_PARTS = {
    "node_modules",
    ".git",
    "__pycache__",
    ".venv",
    "sessions",
    "auth",
    "memory",
    "memories",
}


def _name(value: object) -> str:
    if (
        isinstance(value, str)
        and _NAME.fullmatch(value)
        and not re.search(r"(?:sk[_-]|rk_|whsec_|ghp_|acct_|plugin_asdk_)", value, re.I)
    ):
        return value
    return "redacted-" + hashlib.sha256(str(value).encode()).hexdigest()[:12]


def _read(path: Path, limit: int = 1_048_576) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(descriptor, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("unsupported_metadata_file")
        data = stream.read(limit + 1)
        if len(data) > limit:
            raise ValueError("unsupported_metadata_file")
        return data


def _environment_names(server: dict) -> list[str]:
    values = []
    env = server.get("env", {})
    if isinstance(env, dict):
        values.extend(env.keys())
    if isinstance(server.get("env_vars"), list):
        values.extend(server["env_vars"])
    headers = server.get("env_http_headers", {})
    if isinstance(headers, dict):
        values.extend(headers.values())
    values.append(server.get("bearer_token_env_var"))
    return sorted({v for v in values if isinstance(v, str) and _ENV.fullmatch(v)})


def _endpoint(value: object) -> tuple[str | None, bool]:
    if not isinstance(value, str):
        return None, False
    try:
        parsed = urlsplit(value)
        safe = (
            parsed.scheme == "https"
            and (parsed.hostname, parsed.path) in _PUBLIC_ENDPOINTS
        )
        # Return a reconstructed allowlisted endpoint, never query/fragment,
        # userinfo, custom ports, tenant hostnames or account/project path parts.
        if (
            safe
            and not parsed.username
            and not parsed.password
            and parsed.port in (None, 443)
        ):
            return f"https://{parsed.hostname}{parsed.path}", bool(
                parsed.query or parsed.fragment
            )
    except ValueError:
        pass
    return "<private-endpoint>", True


def _launcher(server: dict) -> dict:
    command = server.get("command")
    if not isinstance(command, str):
        return {}
    executable = Path(command).name
    result = {
        "executable": executable if executable in _EXECUTABLES else "<local-executable>"
    }
    # Scoped npm package identities are reproducible references. Arbitrary
    # arguments (often credentials, database URLs or paths) are never returned.
    if executable == "npx" and isinstance(server.get("args"), list):
        for arg in server["args"]:
            if isinstance(arg, str) and re.fullmatch(
                r"@[a-z0-9_-]+/[a-z0-9_.-]+(?:@[0-9][0-9A-Za-z_.+-]*)?", arg
            ):
                result["package_reference"] = arg
                result["version_pinned"] = bool(re.search(r"@[0-9]", arg))
                break
    return result


def _license(directory: Path, declared: object = None) -> dict:
    if isinstance(declared, str) and declared in _LICENSES:
        return {
            "identifier": declared,
            "basis": "declared",
            "redistribution": "review-required",
        }
    for filename in ("LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"):
        path = directory / filename
        if not path.exists() or path.is_symlink():
            continue
        try:
            text = _read(path, 131_072).decode("utf-8", errors="replace")
        except (OSError, ValueError):
            continue
        markers = [
            ("MIT", "Permission is hereby granted, free of charge"),
            ("Apache-2.0", "Apache License\n"),
            ("MPL-2.0", "Mozilla Public License Version 2.0"),
        ]
        for identifier, marker in markers:
            if marker in text:
                return {
                    "identifier": identifier,
                    "basis": "license-marker",
                    "redistribution": "review-required",
                }
    return {
        "identifier": "unknown",
        "basis": "not-established",
        "redistribution": "not-authorized",
    }


def _source_class(root: Path) -> str:
    if ".system" in root.parts:
        return "runtime-provided"
    if "plugins" in root.parts and "cache" in root.parts:
        return "reference"
    # User-scoped skill installations are references. Project skills retain
    # project ownership, independently of whether their text has a license.
    if root.parent.parent == Path.home():
        return "reference"
    return "private-binding"


def _walk(root: Path, max_entries: int = 30_000):
    if not root.is_dir() or root.is_symlink():
        return
    seen = 0
    for base, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            d
            for d in directories
            if d not in _DENIED_PARTS and not (Path(base) / d).is_symlink()
        )
        if len(Path(base).relative_to(root).parts) >= 6:
            directories[:] = []
        for filename in sorted(files):
            seen += 1
            if seen > max_entries:
                raise ValueError("metadata_entry_limit")
            yield Path(base) / filename


def _skill(path: Path, source: str, disposition: str, provenance: str) -> dict:
    content = _read(path)
    text = content.decode("utf-8")
    match = re.match(r"\A---\s*\n(.*?)\n---(?:\n|$)", text, re.S)
    name = re.search(r"(?m)^name:\s*([^\n]+)$", match.group(1)) if match else None
    if not name:
        raise ValueError("invalid_skill_frontmatter")
    return {
        "name": _name(name.group(1).strip().strip("\"'")),
        "source": source,
        "sha256": hashlib.sha256(content).hexdigest(),
        "provenance": provenance,
        "disposition": disposition,
        "state": "installed",
        "verification": "metadata-only",
        "license": _license(path.parent),
    }


def inventory(
    config_paths: list[Path], skill_roots: list[Path], plugin_roots: list[Path]
) -> dict:
    """Return a shareable inventory, never a backup of local configuration."""
    report = {
        "schema_version": 1,
        "verification": "metadata-only",
        "provider_access": "unverified",
        "mcps": [],
        "skills": [],
        "plugins": [],
        "agents": [],
        "inputs": [],
        "warnings": [],
    }
    for index, path in enumerate(config_paths, 1):
        source = f"config-{index}"
        try:
            path = Path(path)
            if path.name != "config.toml" and not path.name.endswith(".config.toml"):
                raise ValueError("not_a_codex_config_file")
            config = tomllib.loads(_read(Path(path)).decode("utf-8"))
            servers = config.get("mcp_servers", {})
            if not isinstance(servers, dict):
                raise ValueError("invalid_server_table")
            report["inputs"].append({"source": source, "state": "read"})
        except (OSError, ValueError, UnicodeError):
            report["inputs"].append({"source": source, "state": "unavailable"})
            continue
        for name, server in sorted(servers.items()):
            if not isinstance(server, dict):
                report["warnings"].append(
                    {
                        "source": source,
                        "name": _name(name),
                        "reason": "invalid_server_entry",
                    }
                )
                continue
            endpoint, private = _endpoint(server.get("url"))
            launcher = _launcher(server)
            transport = (
                "streamable-http" if endpoint else "stdio" if launcher else "unknown"
            )
            item = {
                "name": _name(name),
                "source": source,
                "transport": transport,
                "state": "configured"
                if server.get("enabled", True) is not False
                else "configured-disabled",
                "disposition": "private-binding"
                if private or launcher.get("executable") == "<local-executable>"
                else "reference",
                "verification": "unverified",
                "env_names": _environment_names(server),
                "authentication": "user-connection-required",
                **launcher,
            }
            if endpoint:
                item["endpoint"] = endpoint
            if transport == "unknown":
                item["disposition"] = "unavailable"
            report["mcps"].append(item)
        agents = path.parent / "agents"
        if agents.is_dir() and not agents.is_symlink():
            for profile in sorted(agents.glob("*.toml")):
                try:
                    content = _read(profile)
                    data = tomllib.loads(content.decode("utf-8"))
                    item = {
                        "name": _name(data.get("name", profile.stem)),
                        "source": source,
                        "sha256": hashlib.sha256(content).hexdigest(),
                        "provenance": "local-agent-profile",
                        "disposition": "private-binding",
                        "state": "installed",
                        "verification": "metadata-only",
                    }
                    if "model" in data:
                        item["model"] = _name(data["model"])
                    if data.get("model_reasoning_effort") in {
                        "low",
                        "medium",
                        "high",
                        "xhigh",
                        "max",
                        "ultra",
                    }:
                        item["reasoning_effort"] = data["model_reasoning_effort"]
                    report["agents"].append(item)
                except (OSError, ValueError, UnicodeError):
                    report["warnings"].append(
                        {"source": source, "reason": "unreadable_agent_profile"}
                    )
    for index, value in enumerate(skill_roots, 1):
        root, source = Path(value), f"skill-root-{index}"
        disposition = _source_class(root)
        try:
            if not root.is_dir() or root.is_symlink():
                raise ValueError("unavailable_skill_root")
            report["inputs"].append({"source": source, "state": "read"})
            for entry in sorted(root.iterdir()):
                if entry.is_symlink():
                    report["skills"].append(
                        {
                            "name": _name(entry.name),
                            "source": source,
                            "sha256": None,
                            "provenance": "symlink-not-followed",
                            "disposition": "unavailable",
                            "state": "present-symlink",
                            "verification": "unverified",
                        }
                    )
            for path in _walk(root):
                if path.name != "SKILL.md":
                    continue
                try:
                    item = _skill(path, source, disposition, "local-entrypoint")
                    report["skills"].append(item)
                except (OSError, ValueError, UnicodeError):
                    report["warnings"].append(
                        {"source": source, "reason": "unreadable_skill_metadata"}
                    )
        except (OSError, ValueError):
            report["warnings"].append(
                {"source": source, "reason": "unavailable_or_truncated_skill_root"}
            )
    seen_plugins = set()
    plugin_metadata = {}
    for index, value in enumerate(plugin_roots, 1):
        root, source = Path(value), f"plugin-root-{index}"
        try:
            if not root.is_dir() or root.is_symlink():
                raise ValueError("unavailable_plugin_root")
            report["inputs"].append({"source": source, "state": "read"})
            for path in _walk(root):
                if path.name == "SKILL.md":
                    try:
                        item = _skill(
                            path, source, "reference", "installed-plugin-entrypoint"
                        )
                        owner = next(
                            (
                                plugin_metadata[p]
                                for p in path.parents
                                if p in plugin_metadata
                            ),
                            None,
                        )
                        if owner:
                            item.update(
                                plugin=owner["name"], plugin_version=owner["version"]
                            )
                        report["skills"].append(item)
                    except (OSError, ValueError, UnicodeError):
                        report["warnings"].append(
                            {"source": source, "reason": "unreadable_plugin_skill"}
                        )
                    continue
                if path.name != "plugin.json":
                    continue
                directory = (
                    path.parent.parent
                    if path.parent.name == ".codex-plugin"
                    else path.parent
                )
                if directory in seen_plugins:
                    continue
                preferred = directory / "plugin.json"
                candidate = preferred if preferred.exists() else path
                try:
                    data = json.loads(_read(candidate))
                    if not isinstance(data, dict) or not data.get("name"):
                        raise ValueError("invalid_plugin_manifest")
                    name = _name(data["name"])
                    version = data.get("version")
                    version = (
                        version
                        if isinstance(version, str) and _VERSION.fullmatch(version)
                        else "unknown"
                    )
                    report["plugins"].append(
                        {
                            "name": name,
                            "version": version,
                            "source": source,
                            "provenance": "installed-manifest",
                            "manifest_sha256": hashlib.sha256(
                                _read(candidate)
                            ).hexdigest(),
                            "state": "installed",
                            "verification": "metadata-only",
                            "license": _license(directory, data.get("license")),
                            "disposition": "bundled"
                            if name == "codex-engineering-platform"
                            else "reference",
                        }
                    )
                    plugin_metadata[directory] = report["plugins"][-1]
                    seen_plugins.add(directory)
                except (OSError, ValueError, UnicodeError):
                    report["warnings"].append(
                        {"source": source, "reason": "unreadable_plugin_manifest"}
                    )
        except (OSError, ValueError):
            report["warnings"].append(
                {"source": source, "reason": "unavailable_or_truncated_plugin_root"}
            )
    for key in ("mcps", "skills", "plugins", "agents"):
        report[key].sort(key=lambda item: (item["name"], item["source"]))
    return report
