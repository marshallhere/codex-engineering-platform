"""Assess local integration eligibility without merging, pushing, or deploying."""

from __future__ import annotations

from pathlib import Path
import re
import subprocess
from .evidence import git


def _git(repo: Path, *args: str) -> str:
    return git(repo, *args)


def assess_integration(
    store, job_id: str, repo: Path, branch: str, accepted_evidence: dict, policy: dict
) -> dict:
    """Only the protected controller may supply verified evidence and policy.

    Eligible decisions retain a lease; caller must release it after revalidation
    and integration. All other paths release it. No remote CI claim is made.
    """
    root = Path(repo).resolve(strict=True)
    result = {
        "feature_accepted": False,
        "merge_eligible": False,
        "deployment_authorized": False,
        "status": "BLOCKED",
        "reasons": [],
        "lease_resource": None,
        "local_only": True,
        "remote_merge_eligible": False,
    }
    resource = f"integration:{root}:{branch}"
    acquired = False

    def deny(reason):
        result["reasons"].append(reason)
        return result

    try:
        job = store.get_job(job_id)
        contract = job["contract"]
        if not isinstance(accepted_evidence, dict) or not isinstance(policy, dict):
            return deny("protected evidence and policy are required")
        if not isinstance(branch, str) or not branch or branch.startswith("-"):
            return deny("invalid integration branch")
        _git(root, "check-ref-format", "--branch", branch)
        if _git(root, "rev-parse", "--show-toplevel") != str(root):
            return deny("repository identity mismatch")
        if accepted_evidence.get("repo") != str(root):
            return deny("evidence belongs to another repository")
        if accepted_evidence.get("contract_digest") != job["contract_digest"]:
            return deny("contract changed; revalidation required")
        for key in ("policy_digest", "spec_digest"):
            frozen = contract.get(key)
            current = policy.get(key)
            if not frozen or accepted_evidence.get(key) != frozen or current != frozen:
                return deny(f"{key} changed or missing; revalidation required")
        candidate = accepted_evidence.get("candidate_sha", "")
        base = accepted_evidence.get("base_sha", "")
        if not all(
            isinstance(oid, str) and re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", oid)
            for oid in (candidate, base)
        ):
            return deny("full immutable candidate and base commit IDs required")
        if _git(root, "rev-parse", "--verify", f"{candidate}^{{commit}}") != candidate:
            return deny("candidate commit identity mismatch")
        if _git(
            root, "rev-parse", "--verify", f"{candidate}^{{tree}}"
        ) != accepted_evidence.get("candidate_tree"):
            return deny("candidate tree changed or missing")
        _git(root, "merge-base", "--is-ancestor", base, candidate)
        required = policy.get("required_gates")
        gates = accepted_evidence.get("gates")
        if (
            not isinstance(required, list)
            or not required
            or any(not isinstance(gate, str) or not gate for gate in required)
            or len(set(required)) != len(required)
            or not isinstance(gates, list)
        ):
            return deny("mandatory gate manifest is missing or malformed")
        by_id = {}
        for gate in gates:
            if (
                not isinstance(gate, dict)
                or not isinstance(gate.get("id"), str)
                or gate["id"] in by_id
            ):
                return deny("duplicate or malformed gate identity")
            by_id[gate["id"]] = gate
        for name in required:
            gate = by_id.get(name, {})
            if (
                gate.get("status") != "PASSED"
                or gate.get("candidate_sha") != candidate
                or gate.get("contract_digest") != job["contract_digest"]
            ):
                return deny(f"mandatory gate {name} failed, missing, or stale")
        review = accepted_evidence.get("review", {})
        if (
            not isinstance(review, dict)
            or review.get("status") != "PASSED"
            or review.get("independent") is not True
            or review.get("candidate_sha") != candidate
            or review.get("contract_digest") != job["contract_digest"]
        ):
            return deny("independent review missing, failed, or stale")
        if job["status"] in {"BLOCKED", "CANCELLED", "WAITING_INPUT"}:
            return deny(f"job is {job['status']}")
        result["feature_accepted"] = True
        result["status"] = "FEATURE_ACCEPTED"
        allowed, categories = policy.get("allow_auto_merge"), contract.get("categories")
        if (
            not isinstance(allowed, list)
            or not allowed
            or not isinstance(categories, list)
            or not categories
            or any(not isinstance(x, str) for x in allowed + categories)
            or accepted_evidence.get("categories") != categories
            or not set(categories).issubset(set(allowed))
        ):
            return deny("automatic merge is unconfigured or category is not allowed")
        if (
            policy.get("deployment_on_merge") is True
            and policy.get("deployment_authorized") is not True
        ):
            return deny(
                "branch merge triggers deployment without separate authorization"
            )
        acquired = store.acquire_lease(resource, job_id)
        if not acquired:
            return deny("integration branch is leased by another job")
        current = _git(root, "rev-parse", "--verify", f"refs/heads/{branch}^{{commit}}")
        if current != base:
            return deny("integration base moved; revalidation required")
        result.update(
            merge_eligible=True,
            status="MERGE_ELIGIBLE",
            lease_resource=resource,
            deployment_authorized=policy.get("deployment_authorized") is True,
            remote_merge_eligible=policy.get("remote_ci_verified") is True,
        )
        store.event(
            job_id,
            "INTEGRATION_ELIGIBLE",
            {
                "resource": resource,
                "base_sha": base,
                "candidate_sha": candidate,
                "local_only": True,
            },
        )
        return result
    except (ValueError, KeyError, OSError, subprocess.TimeoutExpired) as error:
        return deny(str(error))
    finally:
        if acquired and not result["merge_eligible"]:
            store.release_lease(resource, job_id)
