"""Protected black-box gates for an intentionally defective Python CLI fixture."""

from __future__ import annotations

import argparse
import ast
from decimal import Decimal
import json
from pathlib import Path
import shutil
import subprocess
import os
import sys
import tempfile

from .specs import load_change
from .process import run_process

KINDS = {"spec", "tests", "security", "quality"}
REQUIREMENTS = {"DEMO-LIST", "DEMO-INPUT", "DEMO-BOUNDARY"}


def fixture_path() -> Path:
    dev = Path(__file__).resolve().parents[2] / "examples/python-task-cli"
    return (
        dev
        if dev.is_dir()
        else Path(__file__).resolve().parent / "fixtures/python-task-cli"
    )


def bootstrap_demo(target: Path, fixture: Path | None = None) -> Path:
    if fixture is None:
        fixture = fixture_path()
    if target.exists():
        raise ValueError("Demo target already exists")
    shutil.copytree(fixture, target)
    for args in (
        ["init", "--template=", "-b", "main"],
        ["add", "."],
        [
            "-c",
            "user.name=CEP Fixture",
            "-c",
            "user.email=fixture@example.invalid",
            "commit",
            "-m",
            "test: seed deliberately failing acceptance feature",
        ],
    ):
        git_binary = shutil.which("git")
        if not git_binary:
            raise ValueError("Git is required for disposable fixtures")
        subprocess.run(
            [
                str(Path(git_binary).resolve()),
                "-c",
                "core.hooksPath=" + os.devnull,
                *args,
            ],
            cwd=target,
            check=True,
            capture_output=True,
            env={
                "PATH": os.defpath,
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": os.devnull,
            },
        )
    return target


def run_demo_gate(
    repo: Path, kind: str, *, executor=None, scratch_root: Path | None = None
) -> dict:
    if kind not in KINDS:
        raise ValueError("Unknown demo gate kind")
    repo = repo.resolve(strict=True)
    checks = []

    def record(name, requirement, passed, detail=""):
        checks.append(
            {
                "id": name,
                "requirement_id": requirement,
                "passed": bool(passed),
                "detail": detail,
            }
        )

    if kind == "spec":
        try:
            spec = load_change(repo, "list-unfinished")
            record(
                "stable-requirements",
                "DEMO-LIST",
                set(spec["requirement_ids"]) == REQUIREMENTS,
            )
        except (OSError, ValueError) as exc:
            record("stable-requirements", "DEMO-LIST", False, str(exc))
    elif kind == "quality":
        try:
            source = (repo / "task_cli.py").read_text()
            tree = ast.parse(source)
            compile(tree, "task_cli.py", "exec")
            record("python-compile", "DEMO-INPUT", True)
            forbidden = [
                n
                for n in ast.walk(tree)
                if isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id in {"eval", "exec"}
            ]
            record("no-dynamic-input-execution", "DEMO-INPUT", not forbidden)
        except (OSError, SyntaxError) as exc:
            record("python-compile", "DEMO-INPUT", False, type(exc).__name__)
    else:
        # Fixtures belong to the protected harness, not to the evaluated checkout.
        with tempfile.TemporaryDirectory(
            prefix="cep-demo-input-", dir=scratch_root
        ) as directory:
            scratch = Path(directory)
            root = scratch / "root"
            root.mkdir()
            path = root / "tasks.json"
            unfinished = {"id": "two", "title": "unfinished", "done": False}
            inventory = {
                "tasks": [{"id": "one", "title": "complete", "done": True}, unfinished]
            }
            path.write_text(json.dumps(inventory))

            def call(file="tasks.json"):
                args = [
                    sys.executable,
                    "-I",
                    str(repo / "task_cli.py"),
                    "--root",
                    str(root),
                    "--file",
                    file,
                ]
                result = executor(args) if executor else run_process(args, repo, 10)
                if result.get("timed_out") or result.get("output_exceeded"):
                    record(
                        f"execution-limit-{len(checks)}",
                        "DEMO-INPUT" if kind == "tests" else "DEMO-BOUNDARY",
                        False,
                        "Execution timed out"
                        if result.get("timed_out")
                        else "Execution output limit exceeded",
                    )
                return result

            def reject(name, requirement, file="tasks.json"):
                before = {
                    p.name: p.read_bytes()
                    for p in root.iterdir()
                    if p.is_file() and not p.is_symlink()
                }
                result = call(file)
                after = {
                    p.name: p.read_bytes()
                    for p in root.iterdir()
                    if p.is_file() and not p.is_symlink()
                }
                record(
                    name,
                    requirement,
                    result["exit_code"] != 0
                    and bool(result["stderr"].strip())
                    and "Traceback" not in result["stderr"]
                    and not result["stdout"].strip()
                    and before == after,
                    "nonzero, concise error, no output or input mutation required",
                )

            if kind == "tests":
                result = call()
                try:
                    output = json.loads(result["stdout"])
                except ValueError:
                    output = None
                record(
                    "unfinished-in-order",
                    "DEMO-LIST",
                    result["exit_code"] == 0 and output == {"tasks": [unfinished]},
                )
                numeric = (
                    '{"tasks":[{"id":"x","title":"number","done":false,"value":1e400}]}'
                )
                path.write_text(numeric)
                result = call()
                try:
                    output = json.loads(
                        result["stdout"],
                        parse_float=Decimal,
                        parse_constant=lambda value: (_ for _ in ()).throw(
                            ValueError(value)
                        ),
                    )
                except ValueError:
                    output = None
                record(
                    "preserve-large-json-number",
                    "DEMO-LIST",
                    result["exit_code"] == 0
                    and output == json.loads(numeric, parse_float=Decimal),
                )
                deep = (
                    '{"tasks":[{"id":"deep","title":"nested","done":false,"value":'
                    + "[" * 600
                    + "0"
                    + "]" * 600
                    + "}]}"
                )
                path.write_text(deep)
                result = call()
                try:
                    output = json.loads(result["stdout"])
                except (ValueError, RecursionError):
                    output = None
                record(
                    "preserve-deep-json-value",
                    "DEMO-LIST",
                    result["exit_code"] == 0 and output == json.loads(deep),
                )
                for name, data in (
                    ("all-done", {"tasks": [inventory["tasks"][0]]}),
                    ("empty", {"tasks": []}),
                ):
                    path.write_text(json.dumps(data))
                    result = call()
                    try:
                        output = json.loads(result["stdout"])
                    except ValueError:
                        output = None
                    record(
                        name,
                        "DEMO-LIST",
                        result["exit_code"] == 0 and output == {"tasks": []},
                    )
                for name, text in (
                    ("malformed", "{broken"),
                    ("bad-done", '{"tasks":[{"id":"x","title":"x","done":"false"}]}'),
                    ("missing-tasks", "{}"),
                    ("bad-id", '{"tasks":[{"id":"","title":"x","done":false}]}'),
                ):
                    path.write_text(text)
                    reject(name, "DEMO-INPUT")
                path.write_text(
                    '{"tasks":[{"id":"x","title":"x","done":false,"value":NaN}]}'
                )
                reject("non-json-constant", "DEMO-INPUT")
                reject("missing-file", "DEMO-INPUT", "missing.json")
            else:
                outside = scratch / "outside.json"
                outside.write_text(
                    '{"tasks":[{"id":"sentinel","title":"private sentinel","done":false}]}'
                )
                (root / "escape.json").symlink_to(outside)
                reject("traversal", "DEMO-BOUNDARY", "../outside.json")
                reject("absolute-path", "DEMO-BOUNDARY", str(outside))
                reject("symlink-escape", "DEMO-BOUNDARY", "escape.json")
    return {
        "kind": kind,
        "passed": bool(checks) and all(c["passed"] for c in checks),
        "checks": checks,
        "requirement_ids": sorted({c["requirement_id"] for c in checks}),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--kind", choices=sorted(KINDS), required=True)
    args = parser.parse_args()
    result = run_demo_gate(args.repo, args.kind)
    print(json.dumps(result))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
