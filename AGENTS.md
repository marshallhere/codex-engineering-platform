# Codex Engineering Platform

Codex is the only coding assistant. Read HANDOFF_FOR_CODEX.md and docs/DECISIONS.md.
Work on a feature branch. Preserve the original project/ and supervisor/ prototype
as historical scaffolding; the installable runtime lives in src/cep.

Use Python 3.11+ (this Mac: python3.14), standard library runtime dependencies,
and pinned development tools. Run `PYTHONPATH=src python3.14 -m unittest discover -s tests -v`
and both original prototype suites. Never weaken gates or acceptance fixtures.

Meaningful behavior changes require OpenSpec requirements and traceable tests.
Maintain docs/progress/WORK_LOG.md with executed commands, outcomes and blockers.
No live completion claims from mocked tests. Unsupported security boundaries fail closed.
Independent acceptance review runs in a separate restricted Codex root session;
specialist subagent instructions alone are not isolation. Delegate bounded work
with disjoint file ownership. Keep credentials and machine bindings out of Git.

The core must remain technology-independent; packs own technology-specific behavior.
Project setup preserves existing instructions, tools and user edits. Eventu-specific
configuration remains in eventu-tooling. Approved real-project pilots use private frozen
Eventu snapshots; preserve original checkouts and reconcile patches before integration.
Read docs/REAL_PROJECTS.md for external grading, executable bindings and native limits.
