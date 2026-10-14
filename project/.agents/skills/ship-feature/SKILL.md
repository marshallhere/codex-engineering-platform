---
name: ship-feature
description: Implement a scoped product feature with a planned multi-agent workflow and evidence-based quality gates.
---

# ship-feature

Use for medium/large feature work. At the start read AGENTS.md, invariants and relevant ADRs/lessons. Define an acceptance checklist and risk level. Delegate architecture/research/security investigations when relevant, then pick exactly the implementation specialists needed. Parallelize independent file areas only; consolidate before test runs. Request test_designer to add meaningful regressions, test_runner to execute checks, browser_qa for UI, security_reviewer for relevant risk, documentation_engineer for behavior/API changes, code_reviewer for nontrivial changes. Run `python3 scripts/quality_gate.py --stage pr` and mark BLOCKED if missing/failed. Report files, actual test outputs, risks, decisions and proposed lessons. Never claim that an agent ran unless it did.
