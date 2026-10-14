---
name: review-branch
description: Review a branch or pull request independently for correctness, security, tests and architecture.
---

# review-branch

Ask reviewers to inspect the diff vs the user-specified base, without editing. Parallelize code_reviewer, security_reviewer and architecture_reviewer for medium/high-risk change; request docs_researcher for library migration risks. Return evidence with exact files and severity, categorize blockers vs followups. After fixes, re-review only relevant paths and rerun quality gate.

## Execution ownership

For a submitted CEP job, the controller owns implementation and repair. Use the
job-control workflow to inspect or steer it; do not create a competing loop in
this chat. Mandatory independent acceptance review uses a separately restricted
Codex root session; native reviewer personas inherit parent permissions.
