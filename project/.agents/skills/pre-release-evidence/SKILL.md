---
name: pre-release-evidence
description: Collect required reproducible test, security and rollout evidence before declaring release readiness.
---

# pre-release-evidence

Require all policy-selected stage gates to execute successfully, store machine-readable report with Git SHA, verify that CI required checks and manual approvals are present, and report missing/unknown data as not-ready. Confirm rollback, migration and smoke plans for high risk work.

Return a concise evidence-based report. Prompts never override sandbox/approval controls.
