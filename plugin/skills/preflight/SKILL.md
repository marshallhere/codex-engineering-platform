---
name: preflight
description: Execute explicit quality, security and regression gates before handoff or merge.
---

# preflight

Run the project's qualified gate commands from its approved acceptance policy; inspect exact outputs. Ask test_runner to reproduce failures, security_reviewer to assess security issues and browser_qa for UI release pathways where appropriate. Do not turn failures into warnings or edit tests to fake green. Emit a concise green/red evidence report listing executed checks, skipped checks, blockers, release risk and a recommendation for human sign-off.

## Execution ownership

For a submitted CEP job, the controller owns implementation and repair. Use the
job-control workflow to inspect or steer it; do not create a competing loop in
this chat. Mandatory independent acceptance review uses a separately restricted
Codex root session; native reviewer personas inherit parent permissions.
