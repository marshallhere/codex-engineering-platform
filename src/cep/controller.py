"""Deterministic, candidate-bound implementation/check/review/repair controller."""

from __future__ import annotations

import json
import fcntl
import sys
import time
from pathlib import Path

from .evidence import (
    content_manifest,
    digest_json,
    snapshot,
    verify_snapshot,
    worktree,
    write_json,
    runtime_digest,
)
from .sandbox import NativeSandbox
from .specs import load_change
from .state import Store
from .transport import CodexTransport, configured_model

MANDATORY = {"spec", "tests", "security", "quality"}
UI = {"design", "storybook", "browser", "accessibility"}


def protected_manifest(entries: dict, roots: list[str]) -> dict:
    return {
        name: entry
        for name, entry in entries.items()
        if any(
            part in {"tests", "test", "__tests__", ".codex"}
            for part in Path(name).parts
        )
        or Path(name).name.startswith("test_")
        or Path(name).name in {"conftest.py", "pytest.ini", "tox.ini"}
        or Path(name).name.endswith(("_test.go", ".test.ts", ".spec.ts", ".test.tsx"))
        or any(name == p or name.startswith(p.rstrip("/") + "/") for p in roots)
    }


def load_policy(path: Path, repo: Path, requirements: list[str]) -> dict:
    path = path.resolve(strict=True)
    if path.is_relative_to(repo.resolve()):
        raise ValueError("Acceptance policy must be outside worker repository")
    policy = json.loads(path.read_text())
    if policy.get("schema_version") != 1:
        raise ValueError("Unsupported policy schema")
    checks = policy.get("checks")
    if not isinstance(checks, list) or not checks:
        raise ValueError("Real acceptance commands are required")
    ids, kinds, coverage = set(), set(), set()
    for check in checks:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("id"), str)
            or not check["id"]
        ):
            raise ValueError("Each gate requires an ID")
        if check["id"] in ids:
            raise ValueError("Duplicate gate")
        ids.add(check["id"])
        kinds.add(check.get("kind"))
        args = check.get("argv")
        if check.get("adapter") == "protected-python-demo":
            args = [str(Path(sys.executable).resolve())]
        if (
            not isinstance(args, list)
            or not args
            or any(not isinstance(a, str) or not a for a in args)
        ):
            raise ValueError("Gate requires argv, never shell commands")
        if not Path(args[0]).is_absolute():
            raise ValueError("Gate executable must be operator-resolved and absolute")
        mapped = check.get("requirements", [])
        if not isinstance(mapped, list) or any(r not in requirements for r in mapped):
            raise ValueError("Gate requirement mapping is invalid")
        coverage.update(mapped)
        timeout = check.get("timeout_seconds", 120)
        if type(timeout) is not int or not 1 <= timeout <= 3600:
            raise ValueError("Invalid gate timeout")
    required = MANDATORY | (UI if policy.get("ui") else set())
    if not required.issubset(kinds) or set(requirements) - coverage:
        raise ValueError("Missing mandatory gate categories or requirement evidence")
    for field in ("max_attempts", "max_stagnant"):
        value = policy.get(field, 12 if field == "max_attempts" else 3)
        if type(value) is not int or value <= 0:
            raise ValueError("Positive retry limits required")
    return policy


class Controller:
    def __init__(self, control: Path, *, sandbox=None, transport=None):
        self.store = Store(control)
        self.sandbox = sandbox
        self.transport = transport

    def submit(
        self,
        repo: Path,
        spec: str,
        policy_path: Path,
        budget_seconds: float,
        *,
        token_budget: int | None = None,
    ) -> dict:
        if token_budget is not None:
            raise ValueError(
                "Token-cap enforcement is not yet qualified; use an explicit time budget"
            )
        repo = repo.resolve(strict=True)
        change = load_change(repo, spec)
        policy = load_policy(policy_path, repo, change["requirement_ids"])
        if self.store.control.is_relative_to(repo):
            raise ValueError("Control state must remain outside project")
        manifest = content_manifest(repo)
        protected = policy.get("protected_paths", [])
        if not isinstance(protected, list) or any(
            not isinstance(p, str) or Path(p).is_absolute() or ".." in Path(p).parts
            for p in protected
        ):
            raise ValueError("Protected evidence paths must be relative")
        initial = protected_manifest(manifest["files"], protected)
        protected = sorted(
            set(protected)
            | {
                str(Path(name).parent)
                for name in initial
                if Path(name).parent != Path(".")
            }
        )
        protected_files = protected_manifest(manifest["files"], protected)
        contract = {
            "repo": str(repo),
            "spec": spec,
            "spec_digest": change["digest"],
            "requirements": change["requirement_ids"],
            "policy": policy,
            "policy_path": str(policy_path.resolve()),
            "policy_digest": digest_json(policy),
            "base_sha": manifest["head"],
            "max_attempts": policy.get("max_attempts", 12),
            "execution_mode": "live",
            "model": policy.get("codex_model") or configured_model(),
            "runtime_digest": runtime_digest(),
            "protected_files": protected_files,
            "protected_roots": protected,
        }
        job = self.store.create_job(contract, budget_seconds)
        try:
            tree = worktree(
                repo, self.store.control / "worktrees" / job["id"], job["id"]
            )
        except Exception:
            self.store.set_status(job["id"], "BLOCKED", "Worktree preparation failed")
            raise
        self.store.event(job["id"], "WORKTREE", tree)
        write_json(
            self.store.control / "jobs" / (job["id"] + ".json"), {"worktree": tree}
        )
        return self.store.get_job(job["id"])

    def _tree(self, job_id: str) -> Path:
        obj = json.loads((self.store.control / "jobs" / (job_id + ".json")).read_text())
        return Path(obj["worktree"]["path"])

    def _validate(self, job: dict, tree: Path):
        contract = job["contract"]
        if contract.get("runtime_digest") != runtime_digest():
            raise ValueError(
                "Runtime changed or unversioned contract; create a new qualified job"
            )
        policy = json.loads(Path(contract["policy_path"]).read_text())
        if digest_json(policy) != contract["policy_digest"]:
            raise ValueError("Policy changed; create a new reviewed contract")
        if load_change(tree, contract["spec"])["digest"] != contract["spec_digest"]:
            raise ValueError("OpenSpec contract changed; previous evidence is invalid")
        current = content_manifest(tree)["files"]
        if (
            protected_manifest(current, contract["protected_roots"])
            != contract["protected_files"]
        ):
            raise ValueError(
                "Protected acceptance tests changed; create a separately reviewed contract"
            )

    def _checks(self, job: dict, candidate: dict, artifact: Path) -> list[dict]:
        results = []
        for check in job["contract"]["policy"]["checks"]:
            if self.store.get_job(job["id"])["status"] == "CANCELLED":
                raise ValueError("Operator cancellation")
            remaining = self.store.get_job(job["id"])["remaining_seconds"]
            if remaining <= 0:
                raise ValueError("Budget exhausted")
            scratch = artifact / ("gate-" + str(len(results)))
            scratch.mkdir()
            args = [a.replace("{candidate}", candidate["path"]) for a in check["argv"]]
            read_roots = tuple(Path(p) for p in check.get("readable_roots", []))
            reservation = self.store.reserve_time(
                job["id"],
                "gate:" + check["id"],
                min(remaining, check.get("timeout_seconds", 120)),
            )
            gate_started = time.monotonic()
            try:
                if check.get("adapter") == "protected-python-demo":
                    from .demo import run_demo_gate

                    start = time.monotonic()
                    bounded = min(remaining, check.get("timeout_seconds", 120))

                    def execute(argv):
                        current_job = self.store.get_job(job["id"])
                        if current_job["status"] == "CANCELLED":
                            raise ValueError("Operator cancellation")
                        left = bounded - (time.monotonic() - start)
                        left = min(left, current_job["remaining_seconds"])
                        if left <= 0:
                            raise ValueError("Budget exhausted before grader dispatch")
                        return self.sandbox.run(
                            argv, Path(candidate["path"]), scratch, min(10, left)
                        )

                    gate = run_demo_gate(
                        Path(candidate["path"]),
                        check["kind"],
                        executor=execute,
                        scratch_root=scratch,
                    )
                    result = {
                        "argv": ["protected-python-demo", check["kind"]],
                        "exit_code": 0 if gate["passed"] else 1,
                        "timed_out": False,
                        "elapsed_seconds": time.monotonic() - start,
                        "stdout": json.dumps(gate),
                        "stderr": "",
                        "gate": gate,
                    }
                else:
                    result = self.sandbox.run(
                        args,
                        Path(candidate["path"]),
                        scratch,
                        min(remaining, check.get("timeout_seconds", 120)),
                        readable=read_roots,
                    )
            finally:
                self.store.finish_time(
                    reservation["reservation_id"], time.monotonic() - gate_started
                )
            result.update(
                id=check["id"],
                kind=check["kind"],
                requirements=check["requirements"],
                candidate_digest=candidate["digest"],
                contract_digest=job["contract_digest"],
                passed=result["exit_code"] == 0
                and not result["timed_out"]
                and not result.get("output_exceeded"),
            )
            if not verify_snapshot(candidate):
                raise ValueError("Candidate mutated during gates")
            write_json(artifact / ("gate-" + str(len(results)) + ".json"), result)
            results.append(result)
        return results

    def run(self, job_id: str) -> dict:
        self.store.get_job(job_id)
        lock_path = self.store.control / "jobs" / (job_id + ".lock")
        with lock_path.open("a") as lock:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return self._run_locked(job_id)

    def _run_locked(self, job_id: str) -> dict:
        job = self.store.get_job(job_id)
        if job["status"] == "CANCELLED":
            return job
        tree = self._tree(job_id)
        try:
            self._validate(job, tree)
        except (ValueError, OSError) as exc:
            self.store.set_status(job_id, "BLOCKED", str(exc))
            return self.store.get_job(job_id)
        if job["status"] == "ACCEPTED":
            proof = self.evidence(job_id)
            if content_manifest(tree)["digest"] != proof["candidate_digest"]:
                self.store.set_status(
                    job_id,
                    "BLOCKED",
                    "Accepted worktree changed; stale acceptance rejected",
                )
            return self.store.get_job(job_id)
        if job["status"] in {"BLOCKED", "CANCELLED", "WAITING_INPUT"}:
            return job
        if not self.store.acquire_lease("run:" + job_id, job_id):
            raise ValueError("Job already has a controller")
        try:
            self.sandbox = self.sandbox or NativeSandbox()
            if isinstance(self.sandbox, NativeSandbox) and any(
                check.get("adapter") != "protected-python-demo"
                for check in job["contract"]["policy"]["checks"]
            ):
                raise ValueError(
                    "Live acceptance requires a qualified protected grading adapter; arbitrary candidate-run test commands are unqualified"
                )
            if isinstance(self.sandbox, NativeSandbox):
                from .demo import fixture_path

                expected = load_change(fixture_path(), "list-unfinished")
                if job["contract"]["spec_digest"] != expected["digest"]:
                    raise ValueError(
                        "Protected Python grading adapter is qualified only for the shipped demo contract"
                    )
            reservation = self.store.reserve_time(
                job_id, "qualification", min(120, job["remaining_seconds"])
            )
            qualified_started = time.monotonic()
            try:
                qualification = (
                    self.sandbox.qualify(timeout_seconds=reservation["max_seconds"])
                    if isinstance(self.sandbox, NativeSandbox)
                    else self.sandbox.qualify()
                )
            finally:
                self.store.finish_time(
                    reservation["reservation_id"], time.monotonic() - qualified_started
                )
            self.store.event(job_id, "QUALIFICATION", qualification)
            if not qualification.get("passed"):
                self.store.set_status(
                    job_id, "BLOCKED", "Native boundary qualification failed"
                )
                return self.store.get_job(job_id)
            self.transport = self.transport or CodexTransport(
                self.sandbox, model=job["contract"].get("model")
            )
            phase, previous, stagnant, last = "implement", {}, 0, None
            polish_done = False
            while True:
                job = self.store.get_job(job_id)
                if job["status"] == "CANCELLED":
                    break
                self._validate(job, tree)
                attempt = self.store.start_attempt(
                    job_id, phase, max_seconds=min(job["remaining_seconds"], 1800)
                )
                artifact = Path(attempt["artifact_path"])
                started = time.monotonic()
                try:
                    prompt = (
                        f"OpenSpec change {job['contract']['spec']}. Phase {phase}. "
                        "Follow its requirements; modify implementation only, not OpenSpec, policy, tests or runtime configuration. "
                        "No production or external-service access. Use routine implementation judgment. "
                        "Return FAIL with findings for consequential choices needing user input. "
                        "For review independently inspect requirements, security, correctness and missing tests; do not edit files. "
                        "For polish perform one focused pass without expanding scope. "
                        "Return the exact current phase and evidence-based verdict. Previous results: "
                        + json.dumps(previous, separators=(",", ":"))[-6000:]
                    )
                    steering = [
                        e["payload"]["message"]
                        for e in self.store.events(job_id)
                        if e["kind"] == "OPERATOR_STEERING"
                    ]
                    if steering:
                        prompt += (
                            " Operator steering within this frozen contract: "
                            + json.dumps(steering[-5:])[-8000:]
                        )
                    review_candidate = None
                    if phase == "review":
                        review_candidate = previous["candidate"]
                        if not verify_snapshot(review_candidate):
                            raise ValueError("Candidate changed before review")
                        target = Path(review_candidate["path"])
                    else:
                        target = tree
                    outcome = self.transport.invoke(
                        target,
                        artifact / "codex",
                        phase,
                        prompt,
                        min(job["remaining_seconds"], 1800),
                    )
                    elapsed = time.monotonic() - started
                    self.store.finish_attempt(attempt["id"], "PASSED", outcome, elapsed)
                    self._validate(job, tree)
                    if outcome.get("questions"):
                        self.store.event(
                            job_id, "QUESTIONS", {"questions": outcome["questions"]}
                        )
                        self.store.set_status(
                            job_id,
                            "WAITING_INPUT",
                            "Consequential decisions require operator input",
                        )
                        break
                    if phase == "review":
                        if not verify_snapshot(review_candidate):
                            raise ValueError("Reviewer changed candidate")
                        if outcome["verdict"] != "PASS" or outcome["blocking_findings"]:
                            previous = {"review_findings": outcome["blocking_findings"]}
                            phase, polish_done = "implement", False
                            continue
                        if polish_done:
                            if (
                                content_manifest(tree)["digest"]
                                != review_candidate["digest"]
                            ):
                                raise ValueError("Worker changed after final gates")
                            is_live = isinstance(self.transport, CodexTransport)
                            proof = {
                                "mandatory_checks_passed": all(
                                    c["passed"] for c in previous["checks"]
                                ),
                                "independent_review_passed": outcome.get("independent")
                                is True,
                                "contract_digest": job["contract_digest"],
                                "candidate_digest": review_candidate["digest"],
                                "candidate": review_candidate,
                                "checks": previous["checks"],
                                "review": outcome,
                                "policy_digest": job["contract"]["policy_digest"],
                                "spec_digest": job["contract"]["spec_digest"],
                                "requirements": job["contract"]["requirements"],
                                "merge_eligible": False,
                                "deployment_authorized": False,
                                "execution_mode": "live" if is_live else "simulation",
                            }
                            write_json(
                                self.store.control
                                / "jobs"
                                / (job_id + ".evidence.json"),
                                proof,
                            )
                            self.store.set_status(
                                job_id,
                                "ACCEPTED" if is_live else "WAITING_INPUT",
                                ""
                                if is_live
                                else "Simulation passed; live acceptance not established",
                                evidence=proof,
                            )
                            break
                        phase, previous = "polish", {}
                    else:
                        current = content_manifest(tree)["digest"]
                        stagnant = stagnant + 1 if current == last else 0
                        last = current
                        candidate = snapshot(
                            tree, self.store.control / "candidates" / attempt["id"]
                        )
                        checks = self._checks(job, candidate, artifact)
                        previous = {"candidate": candidate, "checks": checks}
                        if all(c["passed"] for c in checks):
                            polish_done = phase == "polish"
                            phase = "review"
                        else:
                            phase, polish_done = "implement", False
                        if stagnant >= job["contract"]["policy"].get("max_stagnant", 3):
                            raise ValueError(
                                "No candidate progress across repeated repairs"
                            )
                except Exception as exc:
                    if self.store.get_attempt(attempt["id"])["status"] == "RUNNING":
                        self.store.finish_attempt(
                            attempt["id"],
                            "FAILED",
                            {"error": str(exc)},
                            time.monotonic() - started,
                        )
                    raise
        except (ValueError, RuntimeError, OSError) as exc:
            if self.store.get_job(job_id)["status"] != "CANCELLED":
                self.store.set_status(job_id, "BLOCKED", str(exc))
        finally:
            self.store.release_lease("run:" + job_id, job_id)
        return self.store.get_job(job_id)

    def evidence(self, job_id: str) -> dict:
        self.store.get_job(job_id)
        path = self.store.control / "jobs" / (job_id + ".evidence.json")
        if not path.exists():
            return {
                "job": self.store.get_job(job_id),
                "events": self.store.events(job_id),
                "attempts": self.store.attempts(job_id),
                "accepted": False,
            }
        return json.loads(path.read_text())
