---
name: evaluate-agent-changes
description: Benchmark a change to agent roles, skills, memory retrieval or guardrail rules.
---

# evaluate-agent-changes

Choose an isolated, non-sensitive benchmark case; run control vs treatment with matching budget and multiple seeds; use independent hidden deterministic graders. Compare pass rate, blockers, policy violations, time and tokens; restore fixture after each run. Never let evaluated agent modify grader.

Return a concise evidence-based report. Prompts never override sandbox/approval controls.
