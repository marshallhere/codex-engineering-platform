---
name: autonomous-feature
description: Execute an OpenSpec change autonomously using Codex specialist agents, verifiable acceptance criteria, and a bounded repair/polish loop.
---

# Autonomous spec-driven feature

Use this for one coherent change, not a vague backlog.

1. Read the OpenSpec change, acceptance scenarios, relevant ADRs and approved preferences. Identify allowed scopes and high-risk operations.
2. Build a task DAG with separated ownership. Delegate Java/Python/TypeScript/database/frontend work to suitable native subagents. Avoid simultaneous edits of the same files or shared test environment.
3. Implement small changes and acceptance-derived positive and negative tests. Keep OpenSpec `tasks.md` truthful.
4. Run configured quality checks. Investigate failures, repair root causes, and rerun checks; never weaken assertions, bypass security scans or suppress findings to get green results.
5. Request independent correctness, security and architecture review. Convert actionable findings into repair tasks, prioritize severity, and verify repairs.
6. Polish error handling, accessibility/UX (where applicable), docs and maintainability. Avoid scope creep and style-only churn.
7. Re-run **all** required checks after final edits. Link verified outcomes to specs and tests; record any skipped checks as blockers, not passes.
8. Only declare READY when externally enforced gates pass. If progress stalls, try a distinct strategy once and then preserve state as BLOCKED rather than hallucinating completion.
9. Propose evidence-backed lessons; do not silently mutate authoritative preferences, specs or security policies.

Autonomy applies only within the sandbox. Do not request routine prompts, and do not seek to bypass denied filesystem/network/credential privileges.

## Design branch (UI changes)
- Classify as greenfield or brownfield before implementation; call the corresponding design skill and delegate to design architect or design guardian.
- Obtain component evidence via Storybook MCP / catalog; do not invent unrelated primitives or style values.
- Add UI acceptance scenarios covering responsive layouts, visual states, keyboard and accessibility.
- After frontend changes, run independent visual QA, Playwright screenshot comparisons, component stories and a11y checks. Do not auto-accept golden screenshots; proposals must be tied to an approved design change.
- Include required external `design` checks in the trusted supervisor UI policy, and reiterate until those checks actually pass.

## Execution ownership

For a submitted CEP job, the controller owns implementation and repair. Use the
job-control workflow to inspect or steer it; do not create a competing loop in
this chat. Mandatory independent acceptance review uses a separately restricted
Codex root session; native reviewer personas inherit parent permissions.
