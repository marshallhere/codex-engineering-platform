---
name: review-branch
description: Review a branch or pull request independently for correctness, security, tests and architecture.
---

# review-branch

Ask reviewers to inspect the diff vs the user-specified base, without editing. Parallelize code_reviewer, security_reviewer and architecture_reviewer for medium/high-risk change; request docs_researcher for library migration risks. Return evidence with exact files and severity, categorize blockers vs followups. After fixes, re-review only relevant paths and rerun quality gate.
