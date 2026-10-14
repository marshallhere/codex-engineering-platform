---
name: verify-migration
description: Verify new or changed database migrations and rollout compatibility.
---

# verify-migration

Use a disposable database at previous schema version; apply forward migration; verify constraints, persisted data and critical queries; rehearse compatibility/rollback if supported and safe. Do not connect to production or destroy user data. Return actual execution evidence and untested hazards.

Return a concise evidence-based report. Prompts never override sandbox/approval controls.
