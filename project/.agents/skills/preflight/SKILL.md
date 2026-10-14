---
name: preflight
description: Execute explicit quality, security and regression gates before handoff or merge.
---

# preflight

Run the configured `python3 scripts/quality_gate.py --stage pr` command; inspect exact outputs. Ask test_runner to reproduce failures, security_reviewer to assess security issues and browser_qa for UI release pathways where appropriate. Do not turn failures into warnings or edit tests to fake green. Emit a concise green/red evidence report listing executed checks, skipped checks, blockers, release risk and a recommendation for human sign-off.
