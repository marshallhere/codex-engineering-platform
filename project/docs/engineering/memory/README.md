# Reviewed engineering memory

`approved.jsonl` is empty intentionally. Add one reviewed JSON object per line; do not add examples as if approved truths.

```json
{"id":"LESSON-0001","status":"approved","title":"SQLAlchemy async session ownership","rule":"Each concurrent task owns its own AsyncSession; do not share AsyncSession across asyncio.gather tasks.","paths":["backend/**/*.py"],"keywords":["sqlalchemy","asyncio","transaction"],"evidence":"PR URL and regression test identifier","reviewed_at":"2026-10-14","expires_at":null}
```

The above record is an **illustrative example only**; do not copy without reproducing, validating and approving it in the project. `memory_retrieve.py` enforces `status=approved`, supports expiry and optional path-scoping, ranks lexically and returns at most 3 by default. It does not incorporate native Codex generated memories and is not protected from tampering by a malicious commit; use CODEOWNERS for knowledge/policy files. `prompt_context.py` has no changed paths in its event, so it only injects unscoped keyword-matched lessons. To use path-scoped lessons, call the CLI explicitly with actual affected paths.

Treat user preferences separately in `~/.codex/PREFERENCES.md` and never auto-promote pending lessons. Expire or amend obsolete lessons in a reviewed change.
