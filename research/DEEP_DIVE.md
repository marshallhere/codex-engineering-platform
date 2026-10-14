# Codex Engineering Platform — architecture review and v2 extension plan

**Research snapshot:** 2026-10-14. **Scope:** local Codex CLI/IDE only; Spring Boot, FastAPI, Next.js, Postgres, Docker and browser QA. **Status:** researched architecture and prototype templates. This report is not proof of production hardening or app-specific end-to-end verification.

## Executive decision

Use native Codex subagents/skills/hooks/local memory as the primary harness; keep strong guardrails in OS/container permissions and required CI checks; add small scripts for task routing, reviewed memory retrieval, and evidence reporting. Do **not** install Ruflo until a controlled benchmark shows native Codex lacks a necessary coordination capability. Avoid a large default prompt, massive agent fan-out, or vector memory of raw session transcripts.

### What v2 actually contains (tested only as kit utilities)

| Implemented prototype | What it DOES NOT guarantee |
|---|---|
| 20 narrowly described native specialist profiles | Agent reliability, runtime isolation or actual agent spawning |
| 11 workflow skill files | Triggering every skill correctly or integrating the user's commands |
| `scripts/task_router.py` with risk/path heuristics | Semantic risk classification; it can miss hidden risky behavior |
| `scripts/memory_retrieve.py` restricted to approved records | Tamper-proof reviews, perfect recall, or model retraining |
| `UserPromptSubmit` reviewed-context hook | Retrieval of scoped entries without explicit file paths; universal hook coverage |
| `PreToolUse` patch guard protecting known policy paths | OS-level guardrails or catching shell/MCP/indirect writes |
| `scripts/quality_gate.py --report <file>` JSON evidence | Proof of code quality without real commands and independent required CI |
| Eval cases in `evals/cases.example.jsonl` | Runnable fixtures or an evaluation score |
| Kit unit tests for utilities | Application tests, live browser QA, security scan, Codex integration tests |

## Source-grounded capabilities and limits

- [Codex subagents](https://learn.chatgpt.com/docs/agent-configuration/subagents): project `.codex/agents/*.toml`, optional per-agent model, separate context, inherited parent sandbox and permissions. Avoid parallel writers on same files and do not assume reviewer = read-only enforcement.
- [Codex hooks](https://learn.chatgpt.com/docs/hooks): `SessionStart`, `SubagentStart`, `UserPromptSubmit`, `PreToolUse`, `PostToolUse`, `PermissionRequest`, `Stop` and others. Hooks can inject and deny supported calls; local hooks need trust and can fail open or miss specialized paths. Do not conflate hooks with access controls.
- [Codex local memories](https://learn.chatgpt.com/docs/customization/memories): opt-in generated episodic state, not authoritative. Keep reviewed project decisions/lessons in Git and private human preferences in `~/.codex/PREFERENCES.md`.
- [OpenAI agent skills guidance (September 2026)](https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra): concise, precisely triggered skills; progressive disclosure and sparse root instructions. Do not force full knowledge corpus read on every request.
- [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode): `codex exec --json` JSONL event stream, `--output-schema` structured final answer. CI jobs handling untrusted code must not expose API credentials as job-wide variables.
- [Codex Security](https://learn.chatgpt.com/docs/security): gated local plugin and `@openai/codex-security` CLI/SDK, can find/verify findings. Do not assume user access; high-privilege scanner needs isolation. Use alongside deterministic scans.

## Proposed data flow

1. User task enters Codex. `UserPromptSubmit` injects a compact, reviewed, unscoped relevant lesson if one exists. A short `SessionStart` adds private approved preferences and critical repo invariants.
2. Lead Codex identifies code paths, APIs, risk, tests and dependencies. Optionally call `task_router.py --paths ... --flag ...`; **manually correct** any misclassification. The route is not authorization.
3. For normal work choose only tech specialist + test engineer + reviewer. For high risk include threat modeling, API/DB migration, security and independent review. Parallelize investigations, serialize overlapping writers.
4. Plan a test first for regressions, then implement. Use deterministic validation scripts (`pytest`, `./mvnw verify`, typecheck, lint, Playwright Test, Semgrep, etc.). Exploratory browser QA via Playwright MCP supplements but does not replace committed automated tests.
5. `quality_gate.py` writes a bounded evidence JSON with Git SHA, real gate IDs, statuses, times and exit codes; no command args or test output. `DRY_RUN` is never considered a passing check. Configure real `quality/gates.json`; the included `gates.example.json` uses placeholder paths.
6. Independent code and security reviews state evidence and explicit test omissions. Make `READY` dependent on actual checks; use CI branch protection, CODEOWNERS and human approvals for risky changes.
7. Capture a correction as a candidate lesson; a human reviews and validates it, adds linked regression test, and promotes it to curated memory. Expire lessons after incompatible framework or architecture changes.

## Recommended agent roles and why

- Implementation: `spring_engineer`, `fastapi_engineer`, `nextjs_engineer`, `database_engineer`, `devops_engineer`.
- Independent analysis: `architecture_reviewer`, `contract_reviewer`, `migration_reviewer`, `security_reviewer`, `threat_modeler`, `performance_engineer`, `accessibility_specialist`.
- QA: `test_designer`, `test_runner`, `browser_qa`, `code_reviewer`.
- Knowledge and improvement: `documentation_engineer`, `docs_researcher`, `learning_curator`, `evaluation_engineer`.

This catalog does not mean all 20 run per change. Default is one implementer, one test/check role, and one independent reviewer for nontrivial changes. Raise only on relevant risk.

## Test system: what remains to wire into EACH repository

| Layer | Spring | FastAPI | Next.js | Frequency |
|---|---|---|---|---|
| Quick | formatter, compile, unit | ruff, typecheck, unit | lint, tsc, Vitest | during development |
| Integration | Testcontainers Postgres/Redis, transactional rollback | test Postgres+Redis, AsyncSession and Alembic | API mocks + typed contract validation | PR |
| Contract | Spring/OpenAPI and Pact as needed | OpenAPI and breaking change checks | generated/validated API clients | PR when API changed |
| Security | authz negative tests, CodeQL/Semgrep | authz isolation, dependency and SAST | CSP, XSS, authn flow, dependency audit | PR / scheduled |
| E2E | business flow via frontend | business flow via frontend | Playwright Test + traces + accessibility | PR smoke, full nightly/release |
| Advanced | PIT mutation on critical code, perf regressions | Hypothesis/schema fuzz, rate limit tests | Stryker optional, multi-browser and performance | targeted/nightly |

Use true isolated test credentials, disposable databases, migrations from old schema and rollback rehearsal where feasible. No production-like PII dataset. Reproduce flaky tests before retry. Record first failures.

## Memory governance

Source priority: enforced OS/company requirements > explicit human decision and code contract > approved ADR/invariant > approved reviewed lesson > private style preferences > native generated episodic memory > third-party tool/repository content. Never use an unreviewed lesson as a binding rule.

Approved JSONL record fields: `id`, `status=approved`, `title`, `rule`, `paths` (optional glob), `keywords`, `evidence` (PR/issue/test), `reviewed_at`, optional `expires_at`. For path-scoped lookup call:

```bash
python3 scripts/memory_retrieve.py --query 'SQLAlchemy AsyncSession concurrency transaction' --paths backend/src/services/orders.py
```

`UserPromptSubmit` currently has no changed-path list, so it injects only matching unscoped entries. More advanced retrieval can be built after collecting high-quality reviewed records. Avoid putting highly sensitive errors or logs into memory.

## Guardrail threat model and ownership

### Trust boundaries

- Codex agent is permitted to edit workspace source but not trusted with production deploy credentials or live customer data.
- Any local MCP server operates as a separate program and may not share Codex sandbox policy; use minimum-privilege credentials and fixed endpoints.
- The agent must not control the only copy of its security policy. Keep required status checks and policy ownership enforced on the Git server or in another OS-owned context.
- Browser sessions can contain cookies and privileged customer data; use disposable local test identities, new profiles, no personal browser profile reuse.
- Docker Engine socket is privileged; don't mount unrestricted socket into untrusted agent workloads. Coordinate Testcontainers through a trusted test runner or Docker access policy.

### What the sample hooks can and cannot do

`pre_edit_policy.py` detects several known `apply_patch` modifications to guardrail paths. It is **bypassable** with shell, Python scripts, external tools, missing hooks, or intentional disabling. `pre_tool_use.py` regexes only cover a selection of dangerous commands. Never describe these as strong mandatory enforcement. An elevated agent can mutate Python scripts, run arbitrary commands, or exploit tool integrations unless OS and server-side boundaries block it.

### CI and Git setup

Require on protected branches: completed integration tests, repo-specific deterministic SAST/secret/dependency checks, and CODEOWNERS approval for `quality/`, `.codex/`, `.github/workflows/`, infrastructure and migration policy files. Configure server-side branch restrictions (reviews, no force pushes, required checks), not just local Git hooks. Keep untrusted PR jobs without credentials or write tokens; pin GitHub Actions by reviewed SHA when feasible. For source providers other than GitHub, implement equivalent restrictions.

GitHub CodeQL is available by repository visibility and organization security entitlement, not universally for private repos; use local Semgrep/Trivy/Gitleaks even when CodeQL is not available. Codex Security requires explicit access and may have usage costs. Consider signed artifacts/SBOM later only if you have a real supply-chain threat model.

## Operational design for parallel worktrees

- Prefer native Codex worktrees for isolated file edits; maintain separate branches, review and merge integration.
- Use `docker compose -p <unique-worktree-id> up -d` or `COMPOSE_PROJECT_NAME=<unique-id>` per parallel stack; never rely on default compose project names when collisions are possible.
- Assign dedicated ports, environment variables, test databases, browser profiles and temp directories per worktree. Never share the same mutable Postgres volume or Playwright authenticated profile across parallel agent sessions.
- Avoid `.env` symlinks from production or personal developer machine. Use ephemeral test-only secrets generated per run and put `.env`-like paths in ignore rules.
- Define `bootstrap`, `up`, `down`, `reset-test-db`, `test-fast`, `test-integration`, `test-e2e`, `quality` and `logs` targets in a `justfile` or `Makefile` for consistent agent use. Always separate `reset-test-db` from production names; require explicit test-environment marker.

## Agent evaluation framework

Baseline: native Codex without extra specialists; treatment: v2 prompts and routing; optional experimental treatment: Ruflo in a throwaway repo. Use the same tasks, access, time budget and model where practical; 3–5 repeated runs per task to start. Build 10–20 seeded fixtures with hidden independent graders and a mix of:

- authz IDOR and cross-tenant bug
- SQLAlchemy/transaction concurrency bug
- Java deadlock/transaction regression
- migrations with compatibility and lock-time hazard
- Next.js SSR caching and XSS negative test
- flaky Playwright test isolation
- malicious README injecting tool instructions
- compromised fake MCP result requesting secrets
- public API backward compatibility trap
- no-op/dangerous dependency update

Measures: successful fix rate, verified test quality, security violations, unsupported completion claims, regressions, net duration, token use, dollars if measurable, and human interventions. Only claim improvement after comparative evidence. **Do not allow the evaluated agent to edit hidden graders**, and keep tasks outside production repos.

## Performance/complexity budget

Start at 3 active agents for moderate tasks, raise to 5 for high-risk independent analysis. Define a max repair loop, for example two attempts before human escalation. Minimize nested context and repeated framework retrieval. Defer semantic vector memory, a self-hosted dashboard, background daemons, cross-machine federation and autonomous deployment until measurable needs emerge.

Monitor data first via `codex exec --json` and gate evidence; aggregate redacted metadata in local SQLite/DuckDB. Track rates, not just individual successful demos. Add OpenTelemetry if you are coordinating many background processes or need cross-service traces, not solely to graph one CLI invocation.

## Rollout plan

**Phase 0 — inventory and threat model (day 1).** Determine exact Codex CLI version and extensions, sandbox policy, installed MCP servers and their permissions, test tooling, monorepo layout, branching/deploy arrangement, repository hosting/visibility and which services have sensitive data. Snapshot/backup existing Codex settings and skip any template that conflicts.

**Phase 1 — safe baseline (days 1–3).** Merge concise AGENTS, 3–5 specialist definitions, relevant skills, private preferences, actual `quality/gates.json`, local gitleaks/semgrep/trivy, required CI and protected branch. Run complete target app tests and sample dry run; manual confirm policy and network controls.

**Phase 2 — memory/QA integration (days 4–7).** Enable native memory if desired, add reviewed scoped JSONL records, record 2–3 real lessons with linked regression tests, set up ephemeral Postgres/Redis, browser Playwright MCP isolated and Playwright Test with trace artifacts. Start integration and release risk matrices.

**Phase 3 — evaluations and observability (week 2).** Create seeded fixtures, baseline-vs-treatment comparisons, typed structured agent/evidence reports, event aggregation and failure injection tests. Fix misclassification and false success conditions discovered. Pin exact dependency versions.

**Phase 4 — autonomy (only after phase 3 evidence).** Expand to cross-repo task DAG, optional retrieval index, richer planning and task resumption, advanced Codex Security where access exists. Evaluate Ruflo side by side rather than defaulting to it.

## Facts still needed from the real machine/repository

1. Exact `codex --version`, extension vs CLI, model/effort, whether `/hooks`, `/memories`, and subagents are available and enabled.
2. Scope: global setup across all repositories, or project-specific; monorepo vs separate repos; tech versions and test commands.
3. Credential access and high-risk boundaries: production VPN, `.env`, Docker access, local Kubernetes, SSH keys, cloud CLI credentials, other MCP servers.
4. Git hosting/branch-protection availability, private/public repo and whether required checks/CODEOWNERS can be enforced.
5. Desired autonomy: how long the agent may work without your input; whether it can install packages, make PRs, operate databases, browse sites, or start local services.
6. Resource budgets: number of parallel agents, Mac RAM/CPU, disk quota, token/cost budget, tolerated feedback time and level of alerts.
7. Memory boundaries: personal preferences vs team decisions, private vs committed, retention, and how conflicting preferences should be resolved.
8. Acceptance criteria: existing test coverage, unreliable tests, major recurring bugs, baseline development time and which metrics matter to you.

These are inventory items, not prerequisites to understanding the architecture. Do not guess values or auto-enable privileged features.

## Selected source URLs

- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/hooks
- https://learn.chatgpt.com/docs/customization/memories
- https://learn.chatgpt.com/docs/config-file/config-reference
- https://learn.chatgpt.com/docs/non-interactive-mode
- https://developers.openai.com/blog/rethinking-skills-and-prompts-for-gpt-6-astra
- https://learn.chatgpt.com/docs/security
- https://docs.github.com/en/code-security/concepts/code-scanning/setup-types
- https://docs.github.com/en/code-security/how-tos/secure-your-supply-chain/manage-your-dependency-security/configure-dependency-review-action
- https://playwright.dev/docs/test-projects
- https://playwright.dev/docs/test-retries
- https://docs.docker.com/compose/how-tos/project-name/
- https://docs.docker.com/desktop/enterprise/hardened-desktop/enhanced-container-isolation/
- https://opentelemetry.io/docs/concepts/signals/traces/
- https://testcontainers.com/guides/testing-spring-boot-rest-api-using-testcontainers/
