---
name: ship-feature
description: Implement a scoped product feature with a planned multi-agent workflow and evidence-based quality gates.
---

# ship-feature

Use for medium/large feature work. At the start read AGENTS.md, invariants and relevant ADRs/lessons. Define an acceptance checklist and risk level. Delegate architecture/research/security investigations when relevant, then pick exactly the implementation specialists needed. Parallelize independent file areas only; consolidate before test runs. Request test_designer to add meaningful regressions, test_runner to execute checks, browser_qa for UI, security_reviewer for relevant risk, documentation_engineer for behavior/API changes, code_reviewer for nontrivial changes. Run all project-required gate commands from the approved acceptance policy and mark BLOCKED if missing/failed. Report files, actual test outputs, risks, decisions and proposed lessons. Never claim that an agent ran unless it did.

## Execution ownership

For a submitted CEP job, the controller owns implementation and repair. Use the
job-control workflow to inspect or steer it; do not create a competing loop in
this chat. Mandatory independent acceptance review uses a separately restricted
Codex root session; native reviewer personas inherit parent permissions.
