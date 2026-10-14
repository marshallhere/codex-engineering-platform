# Durable implementation record

## 2026-10-14 — import and baseline

- Read HANDOFF_FOR_CODEX.md and README.md completely; inspected prototype and local setup.
- Original source preserved in commit 6907d96; branch feat/slice-a-b created.
- Verified earlier in this session: 14 supervisor and 43 project tests pass with Python 3.14.7.
  Default Python 3.9 cannot import several modules. These suites mock Codex.
- Installed Codex 0.162.1; Node 24.11.1; OpenSpec registry reports 1.14.1.
- Independent audit found unsafe host gate execution, stale READY, missing candidate
  identity, non-durable attempt reservation, stale output reuse and descendant timeout risks.
- No Eventu changes or provider writes performed. GitHub destination does not yet exist.
- Implementation is in progress; no live platform acceptance has been claimed.

## 2026-10-14 — Slice A and Python vertical implementation

- Built technology-neutral `src/cep` runtime, plugin (22 skills, 28 specialist
  profiles), selective journaled installer, Python/Go packs, external pack loading,
  OpenSpec traceability, isolated worktrees, SQLite jobs/leases/reservations,
  restart accounting, bounded process capture and durable watchdogs.
- Native no-fork macOS Seatbelt blocks outside reads/writes, symlink access,
  reviewer writes, TCP/Unix sockets and detached descendants. Broader sandbox
  detached-fork probe failed first; the narrower boundary replaced it. No fallback
  container or weakened denial probe was used.
- Codex 0.162.1 executed fresh implementation and read-only review sessions with
  personal integrations, hooks and native shell disabled. A protected stdio MCP
  broker provides scoped files/direct commands; no worker control-state methods.
- Original suites: 14 supervisor + 43 project tests passed, retained in
  `.local/prototype-*-tests.log`. New final suite: 115 passed, retained in
  `.local/platform-tests-final.log`. Ruff formatting/checks passed.
- Strict OpenSpec validation passed. OpenSpec 0.17.2 is pinned with zero npm audit
  advisories; 1.14.1's dependency advisories blocked that version. No force-fix used.
- Go 1.27.2 archive checksum verified against official distribution metadata;
  isolated fixture `go test ./...` passed. This is pack conformance, not live Go
  worker qualification.
- Sanitized setup inventory records 14 MCP names, 20 cached plugins, 65 readable
  skills and 11 untraversed linked references. Third-party/private skill contents,
  credentials and machine/account bindings were not copied.
- Actual `codex plugin marketplace add .` and plugin installation passed. Existing
  user configuration was retained; CEP workers explicitly disable plugins.
- Packaging first build exposed missing source assets; explicit asset manifest
  fixed it. Disposable wheel/sdist checks passed (171 checks); final-byte rebuild
  underway. Evidence: `.local/packaging/` and `.local/packaging-final/`.
- Bandit 1.8.6 under Python 3.13: no scanner errors, no MEDIUM/HIGH, 15 LOW
  findings independently reviewed and retained. Python 3.14 AST incompatibility
  prevented using that interpreter for Bandit. See `docs/SECURITY_REVIEW.md`;
  new/material findings are rejected by the reviewed-baseline gate.
- Full reachable-history/index/worktree publication scan passed after replacing
  two misleading dummy secret fixture literals; scanner controls were unchanged.
- Independent audit identified and fixes covered missing gate cancellation
  cleanup, lost interruption budget, installer/worker configuration conflict,
  integration exception import, native file permissions and new files inside
  protected test namespaces. All relevant regressions remain enabled.
- Restricted platform review 01 timed out at 240 seconds; no PASS claim. Its
  intermediate test demonstrated added package initializers bypassing a file-only
  test freeze. Entire existing test namespaces now freeze additions too.
- Restricted core review 02 passed. Final focused review is running against frozen
  runtime bytes. Live surface probe 01 found broker test writes allowed; fixed.
  Probe 02 passed actual native patch, protected broker writes, outside access and
  unknown MCP denials, with all sentinels unchanged. Evidence remains private in
  `.local/restricted-surface-*` and `.local/platform-review-*`.
- Historical live demo 02 ACCEPTED after reviewer-found JSON numeric overflow
  repair, six Codex phases and protected gates; it predates final runtime freezing
  and strengthened overflow regression. It is not final-build acceptance.
- Demo 03 was deliberately CANCELLED for further hardening; its state remained
  terminal. Missing not-yet-created registry cleanup was made idempotent.
- Final live demo 04 is underway against frozen runtime and stronger protected
  black-box checks. No final-run acceptance claimed until its gates/review pass.
- Generic in-process candidate test commands are explicitly unqualified for live
  acceptance. Only the shipped Python contract and external grader are currently
  qualified; arbitrary projects fail closed until their own adapter is qualified.
- Added pinned read-only GitHub verification workflow. Remote CI has not yet run.
  No merges, deployment or Eventu/provider changes were performed.

Current follow-up scope: final live proof/review/package checks and public repository
publication, then project-grade adapters, narrow chat/control MCP, reviewed memory
promotion, remote integration and rendered UI acceptance. See `docs/LIMITATIONS.md`.

### Final audit repair checkpoint

- Final restricted review identified cancellation between CLI cases in one gate;
  the executor now checks cancellation, current remaining budget and gate elapsed
  before every child dispatch. Regression verifies exactly one launch.
- Final review 02 PASS with unchanged runtime digest; the prior FAIL is retained.
- Demo 04 was CANCELLED to apply this fix. Demo 05 is now running on frozen bytes.
- Final static gate PASS with 15 retained reviewed LOW findings; no material findings.
- Final installed-wheel/sdist checks passed 171 checks and byte-matched all 18 runtime
  modules. Artifact hashes are private in `.local/packaging-final/source-match.json`.
- Plugin default global activation was disabled to honor project opt-in; the installed
  plugin remains available. Only CEP's new setting changed; private backup retained.
- Latest full publication scan PASS over 237 Git objects and 237 tracked files;
  `git diff --check` also passed. Remote CI/publication remain pending.

### Public repository and remote verification

- Created public MIT repository `marshallhere/codex-engineering-platform` and
  published feature branch `feat/slice-a-b`, commit fd06c24. Default branch currently
  remains the feature branch; no integration or deployment was performed.
- Remote run 38531450062: macOS native qualification/watchdog job PASS. Linux
  contracts passed regression, original suites, Ruff, OpenSpec, dependency audit,
  reviewed security gate and build; installed-wheel check 158 (`doctor`) FAIL.
- Independent diagnosis reproduced metadata-only doctor unnecessarily requiring
  macOS/Codex. Deferred sandbox construction to `--qualify`; two regression tests
  retain live fail-closed behavior. Packaging diagnostics now identify failed check
  without echoing private stderr. No checks skipped or weakened.
- Latest local platform suite: 117 PASS. Original 57 remain PASS. Final static
  security findings unchanged at 15 reviewed LOW. Remote rerun pending.
- Live demo 05 ACCEPTED: job 9d069548-8789-4c0f-98a7-61ec03b16533,
  321.610 charged active seconds, five phases (implementation twice after failed
  protected checks, independent review, polish, final independent review).
  It binds pre-diagnostics-fix runtime; complete local artifacts are retained.
- Demo 06 is running on the updated frozen runtime. Focused restricted CLI review
  and final rebuild/rerun are pending; do not substitute demo 05 for current bytes.
- Read-only actual Eventu inspection PASS, executed no project commands, found
  `eventu-tooling` ownership and preserved it. Result stays private under `.local`.
