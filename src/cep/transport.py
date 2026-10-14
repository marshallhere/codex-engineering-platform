"""Codex-only structured root sessions; workers inherit no personal integrations."""

from __future__ import annotations

import json
import os
import sys
import tomllib
from pathlib import Path

from .evidence import write_json
from .process import run_process
from .sandbox import NativeSandbox

SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["phase", "verdict", "summary", "blocking_findings", "questions"],
    "properties": {
        "phase": {"type": "string"},
        "verdict": {"type": "string", "enum": ["PASS", "FAIL"]},
        "summary": {"type": "string"},
        "blocking_findings": {"type": "array", "items": {"type": "string"}},
        "questions": {"type": "array", "items": {"type": "string"}},
    },
}


def configured_model() -> str | None:
    config = Path.home() / ".codex/config.toml"
    if not config.exists():
        return None
    value = tomllib.loads(config.read_text()).get("model")
    return value if isinstance(value, str) else None


class CodexTransport:
    def __init__(
        self, sandbox: NativeSandbox, model: str | None = None, *, tool_bindings=None
    ):
        self.sandbox, self.model = sandbox, model
        self.tool_bindings = [] if tool_bindings is None else tool_bindings

    def invoke(
        self, repo: Path, artifact: Path, phase: str, prompt: str, timeout: float
    ) -> dict:
        from .toolchains import validate_bindings

        tools = validate_bindings(self.tool_bindings, repo)
        config = repo / ".codex/config.toml"
        if config.exists():
            allowed = {
                "plugins": {
                    "codex-engineering-platform@codex-engineering-platform": {
                        "enabled": True
                    }
                }
            }
            if config.is_symlink() or tomllib.loads(config.read_text()) != allowed:
                raise ValueError(
                    "Project Codex configuration requires explicit adapter qualification"
                )
        for name in (".codex/hooks.json", "hooks/hooks.json"):
            if (repo / name).exists():
                raise ValueError(
                    "Worker-local runtime configuration requires explicit adapter qualification: "
                    + name
                )
        roles = repo / ".codex/agents"
        if roles.exists():
            permitted = {
                "name",
                "description",
                "developer_instructions",
                "model",
                "model_reasoning_effort",
                "model_reasoning_summary",
            }
            if roles.is_symlink():
                raise ValueError("Project agent profiles require regular files")
            for role in roles.iterdir():
                if (
                    role.is_symlink()
                    or not role.is_file()
                    or role.suffix != ".toml"
                    or role.stat().st_size > 128_000
                ):
                    raise ValueError(
                        "Project agent profiles require bounded regular TOML files"
                    )
                values = tomllib.loads(role.read_text())
                if set(values) - permitted or any(
                    not isinstance(v, str) for v in values.values()
                ):
                    raise ValueError(
                        "Project agent profile authority requires explicit adapter qualification"
                    )
        artifact.mkdir(parents=True, exist_ok=True)
        schema, output = artifact / "schema.json", artifact / "result.json"
        write_json(schema, SCHEMA)
        if output.exists():
            raise ValueError("Attempt output must be unique")
        scratch = artifact / "scratch"
        scratch.mkdir()
        profile = self.sandbox.permissions(
            repo, scratch, writable=phase != "review", readable=tools
        )
        code_root = Path(__file__).resolve().parents[1]
        broker_args = [
            str(Path(sys.executable).resolve()),
            "-I",
            "-c",
            "import sys; sys.path.insert(0,"
            + repr(str(code_root))
            + "); from cep.worker_tools import main; raise SystemExit(main())",
            "--repo",
            str(repo),
            "--scratch",
            str(scratch),
            "--registry",
            str(artifact / "registrations"),
            "--readonly" if phase == "review" else "--writable",
        ]
        for tool in tools:
            broker_args.extend(["--readable-tool", str(tool)])
        broker = (
            "mcp_servers.cep_worker={command="
            + json.dumps(broker_args[0])
            + ",args="
            + json.dumps(broker_args[1:])
            + ",startup_timeout_sec=30}"
        )
        cmd = [
            self.sandbox.codex,
            "exec",
            "--cd",
            str(repo),
            "--ignore-user-config",
            "--ephemeral",
            "--strict-config",
            "--skip-git-repo-check",
            "--json",
            "--output-schema",
            str(schema),
            "--output-last-message",
            str(output),
            "-c",
            'approval_policy="never"',
            "-c",
            'default_permissions="cep"',
            "-c",
            self.sandbox.override(profile),
            "-c",
            'web_search="disabled"',
        ]
        cmd.extend(["-c", broker])
        for tool in (
            "cep_list_files",
            "cep_read_file",
            "cep_apply_file",
            "cep_run_command",
        ):
            cmd.extend(
                ["-c", f'mcp_servers.cep_worker.tools.{tool}.approval_mode="approve"']
            )
        for feature in (
            "hooks",
            "apps",
            "plugins",
            "browser_use",
            "computer_use",
            "image_generation",
            "shell_tool",
            "unified_exec",
        ):
            cmd.extend(["-c", f"features.{feature}=false"])
        if self.model:
            cmd.extend(["--model", self.model])
        cmd.append(
            prompt
            + " Use only cep_worker tools for files and commands. Commands execute without fork capability; invoke Python directly, not a shell. Do not call native shell tools. Python executable: "
            + str(Path(sys.executable).resolve())
        )
        # Only the trusted Codex client retains its own authentication access. Tool
        # processes receive the enforced permissions profile above, not this authority.
        env = {
            k: v
            for k, v in os.environ.items()
            if k in {"PATH", "HOME", "LANG", "LC_ALL", "TMPDIR"}
        }
        from .lifecycle import cleanup_registry

        try:
            result = run_process(
                cmd,
                repo,
                timeout,
                env=env,
                record_argv=cmd[:-1] + ["[PROMPT OMITTED]"],
                registry=artifact / "registrations",
            )
        finally:
            cleanup_registry(artifact / "registrations")
        write_json(artifact / "process.json", result)
        if (
            result["exit_code"] != 0
            or result["timed_out"]
            or result.get("output_exceeded")
            or not output.is_file()
        ):
            raise RuntimeError("Codex session failed; inspect attempt process.json")
        value = json.loads(output.read_text())
        if set(value) != {
            "phase",
            "verdict",
            "summary",
            "blocking_findings",
            "questions",
        }:
            raise ValueError("Codex response does not match required schema")
        if value["phase"] != phase or value["verdict"] not in {"PASS", "FAIL"}:
            raise ValueError("Wrong phase or verdict")
        if not isinstance(value["summary"], str) or not isinstance(
            value["blocking_findings"], list
        ):
            raise ValueError("Malformed Codex response")
        if any(not isinstance(x, str) for x in value["blocking_findings"]):
            raise ValueError("Malformed reviewer findings")
        if not isinstance(value["questions"], list) or any(
            not isinstance(x, str) or not x for x in value["questions"]
        ):
            raise ValueError("Malformed consequential questions")
        if value["verdict"] == "PASS" and (
            value["blocking_findings"] or value["questions"]
        ):
            raise ValueError("Inconsistent reviewer verdict")
        usage = []
        for line in result["stdout"].splitlines():
            try:
                event = json.loads(line)
            except ValueError:
                continue
            if event.get("type") == "turn.completed":
                usage.append(event.get("usage", {}))
        return {
            **value,
            "usage": usage,
            "elapsed_seconds": result["elapsed_seconds"],
            "independent": phase == "review",
            "transport": "codex-exec",
        }
