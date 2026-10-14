# Codex Engineering Platform

A reusable Codex plugin and deterministic local runtime for spec-driven engineering.
Projects opt in selectively; technology packs adapt workflows without core changes.
Codex is the only coding assistant. This is an **early alpha**.

Slice A and the smallest Python Slice B vertical are implemented. Broader execution,
remote integration, reviewed memory automation and UI acceptance remain qualification
work. The original prototype is preserved in `project/`, `supervisor/` and
[its README](docs/prototype/README.original.md).

## Install

Requires Python 3.11+. Live workers require macOS, installed Codex (verified with
0.162.1), and a passing native isolation preflight.

```sh
python3.14 -m venv .venv
.venv/bin/python -m pip install .
source .venv/bin/activate
codex plugin marketplace add .
codex plugin add codex-engineering-platform@codex-engineering-platform
.venv/bin/cep inspect /path/to/project
.venv/bin/cep init /path/to/project
.venv/bin/cep init /path/to/project --apply
.venv/bin/cep doctor --qualify
```

Setup, upgrades, rollback and uninstall default to dry runs. They preserve user
edits and stop on conflicts. Existing project instructions retain ownership.
Plugin skills guide chat; the separate controller owns execution and job state.
For Eventu, `eventu-tooling` continues to own workspace setup and provider scopes.
Codex plugin installation enables it globally by default. For per-project opt-in,
set `enabled = false` in the CEP plugin table in your personal Codex config;
`cep init --apply` writes only the project's activation override.

## Run the vertical proof

```sh
.venv/bin/cep demo --directory /tmp/cep-demo-new --budget-minutes 15 --live
```

The directory must be new. This creates an intentionally broken Python CLI,
freezes its OpenSpec and external acceptance policy, and runs implementation,
protected checks, independent read-only review, repair, polish and revalidation.
Private evidence stays under that directory. Omitting `--live` prepares the job
without launching Codex.

For your own clean Git repository, create an OpenSpec change with stable requirement
IDs and an external policy mapping each requirement to real checks:

The commands below expose the job interface. Live acceptance supports the shipped Python demo and externally owned declarative
JSON CLI cases for qualified in-process project work. See [real-project contracts](docs/REAL_PROJECTS.md).
Fork-dependent builds, providers and rendered UI adapters remain blocked.

```sh
cep run --repo /path/to/project --spec change-name --policy /path/to/private/policy.json --budget-minutes 30 --background
cep status JOB_ID
cep evidence JOB_ID
cep steer JOB_ID --message 'Keep the existing public interface'
cep cancel JOB_ID
cep resume JOB_ID
```

Time budgets are mandatory. Token caps fail closed until enforceable. Jobs have
isolated worktrees, durable reservations and process watchdogs. Acceptance binds
the frozen runtime, policy, spec, exact candidate and final restricted review.
Simulation results never become live acceptance. Merge and deployment are separate.

## Extend and verify

[Technology packs](packs/README.md) declare detection, toolchains, commands,
specialist roles and capabilities. Python and Go ship with the plugin; external
packs need no core edits. Detection does not grant execution permission.
`cep qualify-toolchains` verifies installed in-process recipes without granting forks.
Fork-dependent commands, browser, providers and unknown stacks require qualification.

UI work requires design, Storybook, browser and accessibility gates, component
reuse and approved design direction. The [design workflows](project/docs/design/README.md)
provide scaffolding; they do not substitute for rendered evidence.

```sh
PYTHONPATH=src python3.14 -m unittest discover -s tests -v
python3.14 -m unittest discover -s supervisor/tests -v
python3.14 -m unittest discover -s project/tests -v
npm ci --ignore-scripts
npm run spec:validate
npm audit --audit-level=high
python3.14 scripts/check_publication.py .
```

Read [decisions](docs/DECISIONS.md), [portable setup](docs/LOCAL_SETUP.md),
[progress](docs/progress/WORK_LOG.md) and [limitations](docs/LIMITATIONS.md).
Credentials, proprietary skills, provider identities and machine bindings stay
private. The repository records sanitized capability metadata and provenance.
