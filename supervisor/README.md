# Autonomous Codex Supervisor — experimental prototype

**Codex-only; no Ruflo or Claude Code.** Adds a *durable control plane* above native Codex. Works as an operator-run script, not a background daemon. The OpenSpec change must already exist. It does not implement Beads queue polling, cloud CI, remote notifications or automatic merges. Test the integration against your installed Codex release before relying on it.

## Architecture

```
operator CLI -> external state + trusted policy -> Codex implementation (workspace-write)
                                            -> deterministic quality commands (outside agent)
                                            -> independent Codex review (read-only, fresh context)
                                            -> Codex polish -> recheck -> rereview -> READY
```

For an individual long-running interactive task, **prefer native `/goal`** first (turn on `features.goals` if supported). Use this supervisor if you need **independently checked and restartable feature cycles** outside a single interactive session.

## Deployment steps (read before running)

1. Install Codex and confirm `codex --version`, `codex features list`, `codex exec --help`. Test in a disposable repository first. The prototype has **not** been tested with a live Codex install.
2. Set up an OpenSpec change containing `tasks.md` checkbox entries and behavioral specs. Run `openspec validate` manually.
3. Create a **clean feature-branch worktree**, e.g. `git worktree add ../project-feature -b feature/my-change` (from a clean project with appropriate base branch).
4. **Copy the `supervisor/` folder to a path outside the worktree/repository**, ideally a dedicated user-owned control environment. On a multi-user system, protect it from the agent user by file ownership/OS permissions. Place trusted policy and state outside the worktree too.
5. Adapt `policy.example.json` with **real, installed, pinned** tools and repo-specific commands, then save it outside the target repo as `policy.json`. The sample's checks are placeholders and will not work unchanged for most projects. For frontend changes add a browser/E2E gate. Confirm your toolchain is installed before enabling unattended mode.
6. Run from the *isolated operator environment*, not with broad access to your normal Mac account, SSH agent, password manager, Docker socket, production credentials or sensitive mounted volumes.

```
python3 /private/control/supervisor/runner.py \
  --repo /private/worktrees/project-feature \
  --policy /private/control/policy.json \
  --state-dir /private/control/state/project-feature \
  --spec my-change
```

Use the same command to continue an unfinished run. A terminal state (`READY` or `BLOCKED`) is not automatically restarted. To change a blocker budget or start another task, inspect the evidence, reconfigure trusted policy and create a new task state intentionally. **Do not edit the state file blindly** to bypass checks.

## What READY means

- A Codex implementation/repair pass completed without a subprocess error.
- All configured external commands passed; missing/unavailable commands fail.
- OpenSpec `tasks.md` has at least one checked task and no unchecked tasks (**self-reported**, not proof by itself).
- A separate read-only Codex review returned PASS with no reported material blocking findings.
- A further polish pass ran, then all checks were rerun and a separate review passed again.

This does **not** mean the feature is objectively bug-free, spec coverage was independently verified, security tests cover every concern, browser QA was performed, or the system was integrated with your production CI. That depends on the rigor of your policy commands and tests. An AI PASS is not a substitute for real checks.

## Failure and halting conditions

- No repeatable progress after `max_stagnant` work attempts.
- Maximum attempts or time budget reached (budget includes restarts).
- A required command, OpenSpec change, task file or Codex CLI missing; malformed output; process timeout.
- A review identifies material blockers, which triggers repairs until the budget runs out.
- Worktree or policy safety condition violated.

The external supervisor records only summaries, metadata and exit codes; it discards command stdout/stderr to reduce accidental secret retention. This makes debugging harder and is not a comprehensive data-leak prevention mechanism.

## Security non-goals and production hardening needed

- `approval_policy=never` means *no interactive approval prompts*; `workspace-write` sandbox still restricts agent tools. It is **not** `--yolo`/`danger-full-access`.
- The supervisor, policy and state must run outside the writable worktree; **same-user files are not a strong trust boundary**. Use a container/VM, dedicated user and externally owned branch protections for serious unattended use.
- OS isolation, network allowlists, credential isolation, version-pinned MCP/tools and remote CI with protected rules remain deployment prerequisites.
- Quality scripts in a writable repository can be changed by the implementer. Make trusted CI perform invariant checks against the final commit in a separate environment using host-managed policy.
- The sample has no money-spend cap, token accounting, cross-repository locking or queue manager. Configure limits in your Codex account/provider and supervise the host process separately.
- The reviewer is independent in *context and read-only access* but may still miss defects. Add SAST, contract tests, browser QA and benchmark evals.
- A long-running computer can lose power/sleep; use proper durable queue execution and notifications if unattended multi-day operation is needed.

## Control plane tests

```bash
python3 -m unittest discover -s /private/control/supervisor/tests -v
```

These tests mock Codex. They verify state transitions and fail-closed behavior; they do **not** demonstrate real Codex, browser or OpenSpec integration.

## UI design gate integration (v3 Design extension)
- For tasks with UI impact, launch the supervisor using an operator-owned policy with `require_ui_gate: true` and real `kind: design` commands. This type is now recognized by the runner.
- Copy and customize `project/quality/design-ui-supervisor-checks.example.json` into the protected policy; its commands are NOT automatically installed or considered passing.
- Keep Playwright baselines, screenshots and Storybook stories under version control with a documented baseline provenance. Prevent agents from modifying trusted quality policies or accepting visual regression snapshots just to pass tests.
- A design check that merely runs static analysis is not enough: add a deterministic Playwright visual test, Storybook component and axe a11y checks for the app.
- The supervisor itself has not been fully tested against Codex, OpenSpec or a real browser; treat it as a prototype.
