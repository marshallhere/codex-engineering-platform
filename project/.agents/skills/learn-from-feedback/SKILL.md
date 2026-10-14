---
name: learn-from-feedback
description: Capture verified user preferences, mistakes and engineering lessons for explicit review.
---

# learn-from-feedback

When user corrects an answer or a verified defect teaches a reusable lesson, consult existing preferences, ADRs and lessons. Distinguish a personal preference (update proposal for ~/.codex/PREFERENCES.md) from a project decision (propose an ADR) or a failure prevention rule (lesson + regression test). Ask learning_curator to write a pending proposal under `.codex/learning/pending/`; it must include symptom, root cause, corrected rule, scope, evidence and reproducible test. Do not promote it automatically; present the change for user review. Avoid PII/secrets in proposals. Native Codex memories are non-authoritative, so keep approved standards in versioned files.
