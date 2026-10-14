"""Public operator CLI. Machine bindings and run state are private."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys

from . import __version__
from .controller import Controller
from .evidence import write_json
from .install import install_project, rollback_project, uninstall_project
from .packs import discover_packs
from .project import inspect_project
from .sandbox import NativeSandbox


def bundle_path() -> Path:
    dev = Path(__file__).resolve().parents[2] / "plugin"
    return dev if dev.is_dir() else Path(__file__).resolve().parent / "bundle"


def default_control() -> Path:
    return Path.home() / "Library/Application Support/CodexEngineeringPlatform"


def _background(control: Path, job_id: str) -> dict:
    log = control / "jobs" / (job_id + ".controller.log")
    code = (
        "import sys; sys.path.insert(0,"
        + repr(str(Path(__file__).resolve().parents[1]))
        + "); from cep.cli import main; raise SystemExit(main())"
    )
    args = [
        str(Path(sys.executable).resolve()),
        "-I",
        "-c",
        code,
        "run",
        "--control",
        str(control),
        "--job",
        job_id,
    ]
    with log.open("a", encoding="utf-8") as output:
        proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=output,
            stderr=output,
            start_new_session=True,
        )
    return {
        "job_id": job_id,
        "controller_pid": proc.pid,
        "background": True,
        "log": str(log),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="cep", description="Codex Engineering Platform"
    )
    parser.add_argument("--version", action="version", version=__version__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in (
        "inspect",
        "init",
        "install",
        "upgrade",
        "rollback",
        "uninstall",
        "packs",
    ):
        p = sub.add_parser(name)
        p.add_argument("project", type=Path)
        p.add_argument("--bundle", type=Path, default=bundle_path())
        p.add_argument("--apply", action="store_true")
    p = sub.add_parser("doctor")
    p.add_argument("--qualify", action="store_true")
    p.add_argument("--report", type=Path)
    p = sub.add_parser("run")
    p.add_argument("--repo", type=Path)
    p.add_argument("--spec")
    p.add_argument("--policy", type=Path)
    p.add_argument("--budget-minutes", type=float)
    p.add_argument("--token-budget", type=int)
    p.add_argument("--job")
    p.add_argument("--background", action="store_true")
    p.add_argument("--control", type=Path, default=default_control())
    for name in ("status", "evidence", "resume", "cancel", "steer"):
        p = sub.add_parser(name)
        p.add_argument("job", nargs="?")
        p.add_argument("--control", type=Path, default=default_control())
        if name == "steer":
            p.add_argument("--message", required=True)
    p = sub.add_parser("demo")
    p.add_argument("--directory", type=Path, required=True)
    p.add_argument("--budget-minutes", type=float, required=True)
    p.add_argument(
        "--live", action="store_true", help="Actually launch bounded Codex sessions"
    )
    args = parser.parse_args(argv)
    try:
        command = args.command
        code = 0
        if command == "inspect":
            result = inspect_project(args.project)
        elif command == "packs":
            result = discover_packs(args.bundle / "packs", args.project)
        elif command in {"init", "install", "upgrade"}:
            result = install_project(args.project, args.bundle, apply=args.apply)
            code = 2 if result.get("conflicts") else 0
        elif command in {"rollback", "uninstall"}:
            result = (rollback_project if command == "rollback" else uninstall_project)(
                args.project, apply=args.apply
            )
            code = 2 if result.get("conflicts") else 0
        elif command == "doctor":
            result = (
                NativeSandbox().qualify()
                if args.qualify
                else {
                    "version": __version__,
                    "platform": sys.platform,
                    "live_qualified": False,
                    "next": "cep doctor --qualify",
                }
            )
            if args.qualify and not result["passed"]:
                code = 2
            if args.report:
                write_json(args.report, result)
        elif command == "demo":
            from .demo import bootstrap_demo

            args.directory = args.directory.resolve()
            if args.directory.exists():
                raise ValueError(
                    "Demo directory must be new; existing data is preserved"
                )
            args.directory.mkdir(parents=True)
            repo = bootstrap_demo(args.directory / "project")
            control = args.directory / "control"
            policy = {
                "schema_version": 1,
                "max_attempts": 12,
                "max_stagnant": 3,
                "checks": [
                    {
                        "id": kind,
                        "kind": kind,
                        "adapter": "protected-python-demo",
                        "argv": [str(Path(sys.executable).resolve())],
                        "requirements": ["DEMO-LIST", "DEMO-INPUT", "DEMO-BOUNDARY"],
                        "timeout_seconds": 120,
                    }
                    for kind in ("spec", "tests", "security", "quality")
                ],
            }
            policy_path = args.directory / "policy.json"
            write_json(policy_path, policy)
            engine = Controller(control)
            job = engine.submit(
                repo, "list-unfinished", policy_path, args.budget_minutes * 60
            )
            result = (
                engine.run(job["id"])
                if args.live
                else {
                    "job": job,
                    "executed": False,
                    "next": "cep run --control " + str(control) + " --job " + job["id"],
                }
            )
            code = 2 if result.get("status") == "BLOCKED" else 0
        else:
            engine = Controller(args.control)
            if command == "run":
                if args.job:
                    if any(
                        v is not None
                        for v in (
                            args.repo,
                            args.spec,
                            args.policy,
                            args.budget_minutes,
                            args.token_budget,
                        )
                    ):
                        raise ValueError(
                            "An existing job retains its frozen contract and budget"
                        )
                    job = engine.store.get_job(args.job)
                else:
                    if any(
                        v is None
                        for v in (
                            args.repo,
                            args.spec,
                            args.policy,
                            args.budget_minutes,
                        )
                    ):
                        raise ValueError(
                            "New runs require --repo --spec --policy --budget-minutes"
                        )
                    job = engine.submit(
                        args.repo,
                        args.spec,
                        args.policy,
                        args.budget_minutes * 60,
                        token_budget=args.token_budget,
                    )
                result = (
                    _background(engine.store.control, job["id"])
                    if args.background
                    else engine.run(job["id"])
                )
                code = 2 if result.get("status") == "BLOCKED" else 0
            elif command == "status":
                result = (
                    engine.store.get_job(args.job)
                    if args.job
                    else engine.store.list_jobs()
                )
            elif command == "evidence":
                if not args.job:
                    raise ValueError("Job ID required")
                result = engine.evidence(args.job)
            elif command == "cancel":
                if not args.job:
                    raise ValueError("Job ID required")
                engine.store.set_status(args.job, "CANCELLED", "Operator cancellation")
                from .lifecycle import cleanup_registry

                for attempt in engine.store.attempts(args.job):
                    cleanup_registry(
                        Path(attempt["artifact_path"]) / "codex/registrations"
                    )
                    cleanup_registry(Path(attempt["artifact_path"]) / "registrations")
                result = engine.store.get_job(args.job)
            elif command == "resume":
                if not args.job:
                    raise ValueError("Job ID required")
                # Recovery cannot steal a lease from a live controller.
                import fcntl

                lock_path = engine.store.control / "jobs" / (args.job + ".lock")
                with lock_path.open("a") as lock:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    from .lifecycle import cleanup_registry

                    for attempt in engine.store.attempts(args.job):
                        cleanup_registry(
                            Path(attempt["artifact_path"]) / "codex/registrations"
                        )
                        cleanup_registry(
                            Path(attempt["artifact_path"]) / "registrations"
                        )
                    recovered = engine.store.recover(args.job)
                    if recovered["status"] not in {"BLOCKED", "CANCELLED"}:
                        engine.store.set_status(
                            args.job,
                            "QUEUED",
                            "Explicit resume; boundary requalification required",
                        )
                result = engine.run(args.job)
                code = 2 if result.get("status") == "BLOCKED" else 0
            else:
                if not args.job:
                    raise ValueError("Job ID required")
                engine.store.event(
                    args.job, "OPERATOR_STEERING", {"message": args.message}
                )
                result = {
                    "job_id": args.job,
                    "recorded": True,
                    "note": "Requirement changes require a new contract; authority and budget are unchanged",
                }
        print(json.dumps(result, indent=2, default=str, allow_nan=False))
        return code
    except (ValueError, OSError, RuntimeError, KeyError) as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
