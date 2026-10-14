---
name: job-control
description: Submit, inspect, steer or recover a bounded CEP engineering job with evidence-backed acceptance.
---

Read `cep --help` and the relevant command help; use only operations present in
the installed release. Read the project manifest, OpenSpec change and approved
runtime policy before submitting. Every job needs an explicit active-time
budget, stable requirement IDs, mandatory gates and authorized resources.
Run preflight before a worker can launch. A blocked isolation result means no
worker launch, even when some probes pass. Never bypass that result, swap to an
unrestricted command, or silently use another execution backend.

Once submitted, the CEP controller owns execution. This conversation provides
status and steering; do not implement the same files concurrently or start a
second repair loop. Delegate independent investigations only when they have
separate ownership and resources. Respect existing project permissions.

Native Codex manages conversation history, compaction and its specialist agents.
CEP manages attempt reservations, acceptance checks, recovery and evidence. A
specialist review is useful feedback; mandatory independent review requires a
separate restricted root session on the same candidate as the final gates.

Use recorded job state to distinguish active work, waiting for a consequential
decision, resource prerequisites, interruption and exhausted attempts. Return
precise blockers with artifact references. Never mark skipped checks passed,
broaden permissions after a denial, or reduce requirements to finish.

After reboot, explicitly resume and requalify resources before continuing. A
process launched from a chat is not proof it survives chat closure: claim
detached execution only when the installed controller has passed that test.
Report completion only from the final candidate-bound acceptance record.
