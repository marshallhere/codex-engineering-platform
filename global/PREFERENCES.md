# Personal engineering preferences (local, not checked into project repos)

Status: DRAFT EXAMPLE — review and edit before treating these as personal preferences. Do not place credentials or private customer data here.

- Primary assistant: Codex only. Prefer native capabilities before adding orchestrators.
- I value small, reviewable changes, strongly typed APIs, explicit failure handling, and automated regression tests.
- Prefer discussing trade-offs for impactful architecture changes, then record the chosen option in an ADR.
- My preferred stacks are context-dependent: Java/Spring, Python/FastAPI, TypeScript/React/Next.js, PostgreSQL, Docker.
- Require evidence for claims: real test logs, screenshots/traces for browser failures, actionable security findings.
- If the current repository already has a convention that differs from these preferences, raise the conflict rather than blindly replacing the convention.

## Decisions to ask before setting as preferences

- Formatting and lint configurations by language
- Preferred test frameworks for Java and TypeScript
- Migration approach (Alembic vs Flyway/Liquibase)
- Whether new dependencies need explicit approval
- Whether browser network access is allowed in each environment
