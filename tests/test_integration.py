from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import unittest

from cep.integration import assess_integration
from cep.state import Store


class IntegrationTests(unittest.TestCase):
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
        self.repo = Path(self.temp.name).resolve() / "repo"
        self.repo.mkdir()
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Fixture")
        self.git("config", "user.email", "fixture@example.invalid")
        (self.repo / "feature.txt").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-m", "chore: fixture base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("checkout", "-b", "feature")
        (self.repo / "feature.txt").write_text("candidate\n")
        self.git("commit", "-am", "feat: candidate")
        self.candidate = self.git("rev-parse", "HEAD")
        self.tree = self.git("rev-parse", "HEAD^{tree}")
        self.store = Store(Path(self.temp.name) / "control")
        self.job = self.store.create_job(
            {
                "repo": str(self.repo),
                "spec_digest": "spec",
                "policy_digest": "policy",
                "categories": ["local"],
            },
            100,
        )
        digest = self.job["contract_digest"]
        self.evidence = {
            "repo": str(self.repo),
            "contract_digest": digest,
            "policy_digest": "policy",
            "spec_digest": "spec",
            "candidate_sha": self.candidate,
            "candidate_tree": self.tree,
            "base_sha": self.base,
            "categories": ["local"],
            "gates": [
                {
                    "id": "tests",
                    "status": "PASSED",
                    "candidate_sha": self.candidate,
                    "contract_digest": digest,
                }
            ],
            "review": {
                "status": "PASSED",
                "independent": True,
                "candidate_sha": self.candidate,
                "contract_digest": digest,
            },
        }
        self.policy = {
            "policy_digest": "policy",
            "spec_digest": "spec",
            "required_gates": ["tests"],
            "allow_auto_merge": ["local"],
        }

    def assess(self, evidence=None, policy=None, job=None):
        return assess_integration(
            self.store,
            (job or self.job)["id"],
            self.repo,
            "main",
            self.evidence if evidence is None else evidence,
            self.policy if policy is None else policy,
        )

    def test_local_eligibility_does_not_merge(self):
        self.store.set_status(
            self.job["id"],
            "ACCEPTED",
            evidence={
                "mandatory_checks_passed": True,
                "independent_review_passed": True,
                "contract_digest": self.job["contract_digest"],
            },
        )
        result = self.assess()
        self.assertEqual(result["status"], "MERGE_ELIGIBLE")
        self.assertFalse(result["deployment_authorized"])
        self.assertFalse(result["remote_merge_eligible"])
        self.assertEqual(self.git("rev-parse", "main"), self.base)
        self.assertEqual(self.git("branch", "--show-current"), "feature")
        self.store.release_lease(result["lease_resource"], self.job["id"])

    def test_merge_policy_and_deployment_separate(self):
        policy = dict(self.policy, allow_auto_merge=[])
        result = self.assess(policy=policy)
        self.assertTrue(result["feature_accepted"])
        self.assertFalse(result["merge_eligible"])
        result = self.assess(policy=dict(self.policy, deployment_on_merge=True))
        self.assertFalse(result["merge_eligible"])
        self.assertIn("deployment", result["reasons"][0])

    def test_base_moved_requires_revalidation_and_releases(self):
        self.git("update-ref", "refs/heads/main", self.candidate)
        result = self.assess()
        self.assertFalse(result["merge_eligible"])
        self.assertIn("base moved", result["reasons"][0])
        other = self.store.create_job({"spec_digest": "other"}, 100)
        self.assertTrue(
            self.store.acquire_lease(f"integration:{self.repo}:main", other["id"])
        )

    def test_stale_missing_failed_and_tampered_evidence(self):
        for key, value in (
            ("contract_digest", "stale"),
            ("candidate_tree", "stale"),
            ("repo", str(self.repo / "other")),
            ("gates", []),
        ):
            with self.subTest(key=key):
                evidence = dict(self.evidence, **{key: value})
                self.assertFalse(self.assess(evidence=evidence)["feature_accepted"])
        evidence = deepcopy(self.evidence)
        evidence["gates"][0]["status"] = "FAILED"
        self.assertFalse(self.assess(evidence=evidence)["feature_accepted"])
        self.assertFalse(
            self.assess(policy=dict(self.policy, spec_digest="new"))["feature_accepted"]
        )
        evidence = deepcopy(self.evidence)
        evidence["review"]["independent"] = False
        self.assertFalse(self.assess(evidence=evidence)["feature_accepted"])

    def test_racing_jobs_serialize_integration(self):
        first = self.assess()
        other = self.store.create_job(self.job["contract"], 100)
        # Same frozen contract implies same identity, but leases are per job.
        self.assertEqual(other["contract_digest"], self.job["contract_digest"])
        second = self.assess(job=other)
        self.assertFalse(second["merge_eligible"])
        self.assertIn("leased", second["reasons"][0])
        self.store.release_lease(first["lease_resource"], self.job["id"])
        self.assertTrue(self.assess(job=other)["merge_eligible"])
