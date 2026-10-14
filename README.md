# Codex Engineering Platform v3 + Design Engineering extension

This package retains the v3 autonomous engineering prototype and adds **design-aware agents, skills, docs, a component-reuse guard and required UI-specific supervisor gates (when `require_ui_gate` is enabled)**. It is an engineering scaffold; it has not been validated inside a real installed Codex/Next.js project.

**Includes 26 agent profiles, 18 skills, and 57 passing utility tests** (43 project tests + 14 supervisor tests). These are kit-level checks, not proof of quality in an installed app.

## What is new
- 6 design agents: design_system_architect, design_language_guardian, component_librarian, ux_interaction_designer, visual_qa_reviewer, design_system_maintainer.
- 6 design skills: establish-design-language, audit-existing-design, component-first-ui, visual-quality-loop, evolve-design-system, storybook-component-workflow.
- A DESIGN branch in autonomous-feature skill plus updated Next.js/accessibility conventions.
- docs/design templates for actual project design foundations, component catalog, UI acceptance scenarios, Storybook MCP and visual test workflows.
- A detailed [`project/docs/design/STORYBOOK_INTEGRATION.md`](project/docs/design/STORYBOOK_INTEGRATION.md) with Next.js Vite bootstrap, Codex MCP integration, exact component discovery guidance, and separately required Storybook/browser/accessibility checks.
- `scripts/design_gate.py`: conservative static check for changed UI files with per-project policy, component catalog/stories, literal color checks and baseline file restrictions. Utility tests test this script; it is not proof of visual quality.
- Supervisor understands `kind: design` and `require_ui_gate` policy requiring design, Storybook, browser and accessibility checks. External trusted policy MUST include real browser tests and a11y checks for UI work. Example commands are placeholders.

## Quick start (selectively merge, don't overwrite)
1. Review README and `project/docs/design/README.md` and `project/docs/design/TOOLING.md`.
2. Copy relevant agent TOMLs and skills into your existing Codex repository.
3. Identify GREENFIELD vs BROWNFIELD and create an actual `docs/design/FOUNDATIONS.md` based on approved brief or observed app. Do not deploy example placeholders as design policy.
4. For an existing app, audit components and populate `docs/design/component-catalog.json` based on real code and Storybook. For new shared UI primitives, add story files and catalog entries.
5. Copy `quality/design-policy.example.json` to `quality/design-policy.json` and update paths. Run `python3 scripts/design_gate.py --config quality/design-policy.json --files src/components/ui/YourComponent.tsx` to test a changed component.
6. Set up Storybook (including the `@storybook/addon-mcp` preview integration) and committed Playwright screenshots/interaction/a11y checks for your stack. Add real design + Storybook + browser + accessibility gates to an external **trusted** supervisor policy for UI tasks.
7. Audit and pin MCP tools; no unrestricted agent access to production Figma/project data or credentials.

## Verification
`python3 -m unittest discover -s supervisor/tests -v` and `python3 -m unittest discover -s project/tests -v` test the local kit utilities. A green unit test does **not** prove SDD, UI rendering, or Codex agent orchestration succeeds end-to-end.

See [`supervisor/README.md`](supervisor/README.md), [`project/docs/design/README.md`](project/docs/design/README.md) and [`project/docs/engineering/sdd/README.md`](project/docs/engineering/sdd/README.md).

---

# Codex Engineering Platform v3 — autonomous iteration prototype

This is **v2 plus an experimental autonomous goal/loop layer**, not a preconfigured or production-secure agent harness. Research and scaffolding assembled October 14, 2026. Current official Codex command and hook behavior must be checked against your installed version before use.

## New compared with v2

- `/goal`-driven autonomous feature workflow (native Codex; enable with `codex features enable goals` if available).
- New project skill `project/.agents/skills/autonomous-feature/SKILL.md` and spec-driven contract `project/docs/engineering/sdd/README.md`.
- `supervisor/runner.py`: external, restartable feature-loop prototype using **Codex exclusively**. It invokes Codex implementation/review/polish phases with `codex exec`, runs independently configured test/security/spec gates, and tracks state outside the writable worktree.
- Requires OpenSpec `tasks.md` checkbox completion; external check policies include spec, test, security and quality kinds.
- Includes independent read-only review, final polish and revalidation; bounded attempts, wall-time and stagnation detection; protected-branch and clean-worktree restrictions.
- `supervisor/tests/`: deterministic control-plane tests with mock Codex calls.

## Documentation

Start with [`supervisor/README.md`](supervisor/README.md) before attempting to run the prototype. It contains the threat model, permissions, setup, constraints, example commands, limitations and trust boundaries. The existing v2 docs and code are preserved.

**Do not blindly copy or overwrite** your Codex config, hooks, `.github/`, project instructions or repository policies from this ZIP. Back up and selectively merge them. Config from v2 is a template, not validated against your local release.

## What is missing for a fully unattended production-grade platform

- Installed/runtime-integrated OpenSpec and Beads, branch-aware work queue, automatic goal generation and task scheduling.
- CI-controlled external policy files, protected branch rules, safe app-specific test commands, browser QA and requirement-to-test traceability reports.
- VM/container-level isolation, restricted test identity and networks, controlled dependency installation, project secrets isolation, controlled Git tokens and tool-version pinning.
- Crash-safe daemon/launchd, automatic status notifications, bounded token/cost budgets and differentiated retry policies for transient errors.
- Real Codex/OpenSpec end-to-end integration tests and eval benchmarks. The prototype's unit tests mock Codex; this is **not** verification that the agents will produce high-quality code in your repositories.

## Minimal verification of prototype code

```bash
python3 -m unittest discover -s supervisor/tests -v
python3 -m unittest discover -s project/tests -v
```

When moving to actual feature runs, keep the supervisor, state and trusted policy **outside** the agent-writable worktree (preferably in a separate OS/container security context), and enforce required CI gates independently.
