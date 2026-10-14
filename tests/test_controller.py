"""Offline orchestration simulations; these never establish live acceptance."""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from cep.controller import Controller
from cep.evidence import content_manifest, write_json, snapshot
from cep.process import clean_env, run_process


class SimulatedSandbox:
    def __init__(self, passed=True):
        self.passed = passed

    def qualify(self):
        return {"passed": self.passed, "backend": "offline-simulation"}

    def run(self, argv, repo, scratch, timeout, **kwargs):
        return run_process(argv, repo, timeout, env=clean_env(scratch))


class SimulatedTransport:
    def __init__(self):
        self.phases = []
        self.implementations = 0

    def invoke(self, repo, artifact, phase, prompt, timeout):
        self.phases.append(phase)
        if phase == "implement":
            self.implementations += 1
            # First attempt has a real deterministic failing acceptance command.
            (repo / "feature.py").write_text(
                f"def answer():\n    return {41 if self.implementations == 1 else 42}\n"
            )
        return {
            "phase": phase,
            "verdict": "PASS",
            "summary": "Simulated response",
            "blocking_findings": [],
            "independent": phase == "review",
            "elapsed_seconds": 0.001,
        }


class ControllerTests(unittest.TestCase):
    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.repo), *args],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.repo = self.root / "repo"
        self.repo.mkdir()
        change = self.repo / "openspec/changes/answer"
        (change / "specs/answer").mkdir(parents=True)
        (change / "proposal.md").write_text("Return an answer\n")
        (change / "tasks.md").write_text("- [ ] DEMO-ANSWER: implement answer\n")
        (change / "specs/answer/spec.md").write_text(
            "## ADDED Requirements\n### Requirement: DEMO-ANSWER answer\n"
            "The answer SHALL be 42.\n#### Scenario: Query\n- WHEN queried\n- THEN 42\n"
        )
        (self.repo / "feature.py").write_text("def answer():\n    return 0\n")
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("add", ".")
        self.git("commit", "-m", "chore: simulation fixture")
        self.policy_path = self.root / "policy.json"
        check_script = (
            "import runpy; from pathlib import Path; "
            "module=runpy.run_path('feature.py'); assert module['answer']()==42"
        )
        self.policy = {
            "schema_version": 1,
            "max_attempts": 10,
            "max_stagnant": 3,
            "checks": [
                {
                    "id": kind,
                    "kind": kind,
                    "requirements": ["DEMO-ANSWER"],
                    "argv": [sys.executable, "-I", "-c", check_script],
                    "timeout_seconds": 5,
                }
                for kind in ("spec", "tests", "security", "quality")
            ],
        }
        self.policy_path.write_text(json.dumps(self.policy))
        self.transport = SimulatedTransport()
        self.controller = Controller(
            self.root / "control", sandbox=SimulatedSandbox(), transport=self.transport
        )
        self.job = self.controller.submit(self.repo, "answer", self.policy_path, 60)

    def test_real_failed_gate_repairs_and_polishes_but_simulation_not_accepted(self):
        final = self.controller.run(self.job["id"])
        self.assertEqual(final["status"], "WAITING_INPUT")
        self.assertEqual(
            self.transport.phases,
            ["implement", "implement", "review", "polish", "review"],
        )
        proof = self.controller.evidence(self.job["id"])
        self.assertEqual(proof["execution_mode"], "simulation")
        self.assertTrue(proof["mandatory_checks_passed"])
        self.assertTrue(proof["independent_review_passed"])
        failed = []
        for path in self.controller.store.control.glob("attempts/*/gate-*.json"):
            gate = json.loads(path.read_text())
            if not gate["passed"]:
                failed.append(gate)
        self.assertTrue(failed)
        self.assertTrue(
            all(
                gate["candidate_digest"] != proof["candidate_digest"] for gate in failed
            )
        )
        self.assertEqual(
            (self.repo / "feature.py").read_text(), "def answer():\n    return 0\n"
        )

    def test_failed_qualification_blocks_before_worker(self):
        self.controller.sandbox.passed = False
        final = self.controller.run(self.job["id"])
        self.assertEqual(final["status"], "BLOCKED")
        self.assertEqual(self.transport.phases, [])

    def test_changed_policy_blocks(self):
        policy = dict(self.policy, max_attempts=20)
        self.policy_path.write_text(json.dumps(policy))
        final = self.controller.run(self.job["id"])
        self.assertEqual(final["status"], "BLOCKED")
        self.assertEqual(self.transport.phases, [])

    def test_changed_spec_blocks(self):
        tree = self.controller._tree(self.job["id"])
        (tree / "openspec/changes/answer/proposal.md").write_text(
            "Changed requirements\n"
        )
        final = self.controller.run(self.job["id"])
        self.assertEqual(final["status"], "BLOCKED")
        self.assertEqual(self.transport.phases, [])

    def test_new_file_in_protected_test_namespace_blocks(self):
        (self.repo / "acceptance").mkdir()
        (self.repo / "acceptance/test_contract.py").write_text("assert True\n")
        self.git("add", ".")
        self.git("commit", "-m", "test: protect acceptance namespace")
        job = self.controller.submit(self.repo, "answer", self.policy_path, 60)
        tree = self.controller._tree(job["id"])
        (tree / "acceptance/__init__.py").write_text("raise SystemExit(0)\n")
        self.assertEqual(self.controller.run(job["id"])["status"], "BLOCKED")
        self.assertEqual(self.transport.phases, [])

    def test_cancelled_job_stays_cancelled_even_if_contract_changes(self):
        self.controller.store.set_status(self.job["id"], "CANCELLED")
        self.policy_path.write_text("{}")
        self.assertEqual(self.controller.run(self.job["id"])["status"], "CANCELLED")

    def test_cancellation_stops_each_blackbox_dispatch(self):
        calls = []

        def cancel_on_first(*args, **kwargs):
            calls.append(args)
            self.controller.store.set_status(self.job["id"], "CANCELLED")
            return {
                "exit_code": 1,
                "stdout": "",
                "stderr": "test cancellation",
                "elapsed_seconds": 0.001,
            }

        self.controller.sandbox.run = cancel_on_first
        job = self.controller.store.get_job(self.job["id"])
        job["contract"]["policy"]["checks"] = [
            {
                "id": "tests",
                "kind": "tests",
                "adapter": "protected-python-demo",
                "argv": [sys.executable],
                "requirements": ["DEMO-ANSWER"],
            }
        ]
        candidate = snapshot(self.controller._tree(job["id"]), self.root / "candidate")
        artifact = self.root / "gate-artifact"
        artifact.mkdir()
        with self.assertRaisesRegex(ValueError, "Operator cancellation"):
            self.controller._checks(job, candidate, artifact)
        self.assertEqual(len(calls), 1)
        self.assertEqual(
            self.controller.store.get_job(job["id"])["status"], "CANCELLED"
        )

    def test_protected_test_changes_block_worker(self):
        self.policy["protected_paths"] = ["feature.py"]
        self.policy_path.write_text(json.dumps(self.policy))
        job = self.controller.submit(self.repo, "answer", self.policy_path, 60)
        final = self.controller.run(job["id"])
        self.assertEqual(final["status"], "BLOCKED")
        self.assertIn(
            "Protected acceptance tests",
            self.controller.store.events(job["id"])[-2]["payload"]["reason"],
        )

    def test_stale_accepted_candidate_is_invalidated(self):
        tree = self.controller._tree(self.job["id"])
        proof = {
            "mandatory_checks_passed": True,
            "independent_review_passed": True,
            "contract_digest": self.job["contract_digest"],
            "candidate_digest": content_manifest(tree)["digest"],
        }
        write_json(
            self.controller.store.control
            / "jobs"
            / (self.job["id"] + ".evidence.json"),
            proof,
        )
        self.controller.store.set_status(self.job["id"], "ACCEPTED", evidence=proof)
        (tree / "feature.py").write_text("def answer():\n    return 43\n")
        final = self.controller.run(self.job["id"])
        self.assertEqual(final["status"], "BLOCKED")
        self.assertEqual(self.transport.phases, [])
