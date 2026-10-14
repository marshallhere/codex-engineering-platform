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

### Grader hardening and passing CI

- Remote run 38532140003 PASS for both Linux contracts and macOS native boundary
  at commit 0ffa5d0. Installed wheel and complete history publication checks passed.
- Restricted metadata-doctor review PASS; qualification still fails closed.
- Installed verified wheel in the platform-local venv. Metadata doctor reports
  unqualified until actual preflight; the prior installed native preflight PASS.
- Background proof PASS: controller survived launcher exit in its own process
  group, started a job, then exited on cancellation with terminal CANCELLED state.
  Evidence `.local/background-proof/summary.json`; only disposable resources used.
- Demo 06 ACCEPTED after seven phases and 413.558 charged seconds. Its reviewer
  found uncaught recursive serialization for valid 600-depth JSON extra fields,
  and the worker repaired it. Added this case to the protected grader rather than
  relying on review alone. Reference test fixture now encodes iteratively.
- Grader child scratch is now separate from read-only input fixtures. Explicit
  attempt registry keeps cancellation cleanup aligned. A native regression verifies
  inputs can be read but writing them is denied and their bytes remain unchanged.
- Latest local suite: 118 PASS; Ruff PASS; static findings remain reviewed LOW only.
- One grader review returned a descriptive phase instead of exact `review` and was
  rejected by strict transport validation. Correctly structured review retry and
  live demo 07 are running against the new frozen runtime.

### Final policy validation checkpoint

- Restricted grader review retry PASS with exact phase and unchanged runtime.
- Remote run 38533403268 PASS for Linux contracts and macOS native boundary at
  fd2b4a4. Final grader package passed all 171 checks and matched release sources.
- Demo 07 ACCEPTED after seven phases and 532.057 charged seconds, including the
  protected 600-depth JSON check and read-only grader input isolation.
- Preflight previously substituted a made-up argv for protected adapters and could
  accept malformed operator argv then fail during gate preparation. Removed that
  substitution; every gate now validates real command fields before job creation.
  Regression covers null, empty, string and non-string element cases. Restricted
  policy-change review PASS, unchanged source digest.
- Native disposable process-signal probe PASS: child signal denied and protected
  process survived; cleanup targeted only its own fixture process. Added regression.
- Final local suite now 120 tests; raw result retained in platform-tests-final.log.
  Demo 08 and final CI/build are running against frozen runtime after this last fix.

### Output-limit closure

- Remote run 38534822579 PASS for all jobs at 5c11194. Demo 08 ACCEPTED after five
  phases and 375.401 charged seconds; its candidate and immutable snapshot verified.
- Final review of bounded-output handling found an exit/kill race: output overflow
  can coexist with exit code zero. Transport now rejects that flag even with a
  valid PASS response. Demo grading records failed timeout/output-limit evidence
  while retaining every semantic case, so a nominally correct JSON response cannot
  mask the resource failure. Three transport and two grading regressions added.
- Independent restricted output-limit review PASS with unchanged source digest.
- Platform suite now 125 PASS; original 57 PASS. Ruff and reviewed static gate PASS.
- Formatter changed runtime bytes after demo 09 started; the frozen-runtime check
  correctly BLOCKED that run. No acceptance claim was made. Demo 10 is the fresh
  final run after formatting; source is frozen and further edits are documentation.
### Administrative case aliases and instruction authority

- Demo 10 ACCEPTED at 0070a39, five Codex phases, 345.032 charged seconds;
  immutable snapshot and runtime digest verified. Remote CI 38537198305 PASS.
- Subsequent disposable macOS probe demonstrated `.CoDeX/config.toml` could alter
  the broker's protected `.codex` marker. No real configuration was touched.
  Broker checks now casefold administrative, spec, test and instruction names;
  credential evidence checks also reject `.ENV` variants.
- Controller now freezes `.agents`, AGENTS.md and AGENTS.override.md, including
  additions and case aliases. Transport rejects project agent profiles containing
  execution-authority keys; instruction-only installed roles remain supported.
- Native denial rules fold the repository and parent prefix as well as protected
  names. Actual testing exposed nonmatching JSON-doubled Seatbelt regex escapes;
  fixed the regex literal encoding before qualification. Eight native tests PASS,
  including configuration, absolute repository and parent aliases with spaces,
  new instruction files, unchanged markers and successful ordinary source writes.
- Independent specialist review PASS for the final closure. Platform suite 133
  PASS; pinned Ruff PASS; static gate retains 15 reviewed LOW findings, no material
  findings; strict OpenSpec and zero-vulnerability npm audit PASS.
- Runtime frozen after formatting. Restricted independent root review, real demo
  11, exact-source packaging and current-revision CI are still pending. Historical
  accepted runs do not establish acceptance for these changed runtime bytes.
### Slice A / smallest qualified Slice B milestone

- Current implementation commit cd3f88f passed remote Linux contracts and macOS
  native-boundary CI: https://github.com/marshallhere/codex-engineering-platform/actions/runs/38543600374.
- Restricted independent root review PASS with unchanged runtime digest. Its
  fixture-creation/SQLite tests were unavailable within read-only restrictions;
  those restrictions were retained. The full local and CI suites passed separately.
- Demo 11 ACCEPTED, job 3d0a4345-a8c8-4ab6-b66e-5903ed3a1ef0, six actual Codex
  phases: three implementations following failing gates, review, polish, final
  review. Active-time charge 369.726 seconds within the explicit 900-second budget.
- All four final protected gates passed (17 cases). Immutable candidate verified,
  frozen runtime digest equals current bytes, and idempotent controller rerun
  retained ACCEPTED. Sanitized public proof: docs/evidence/slice-a-b.json; complete
  raw artifacts remain ignored under .local/live-demo-11 and review directories.
- Exact-source distributables passed 171 packaging checks and all 112 runtime,
  asset and check-file comparisons. Platform 133 tests + original 57 tests PASS;
  OpenSpec, dependency audit, lint, static security and publication checks PASS.
- Checked only the scoped A/B OpenSpec tasks. Full-platform acceptance is still
  incomplete: live UI/Storybook/visual/accessibility adapters, independently graded
  additional stacks, reviewed-memory promotion/retrieval/evals, chat-control MCP
  and actual remote integration remain pending as recorded in docs/LIMITATIONS.md.
  Fork-dependent build tools are blocked by the current qualified native boundary;
  broader execution must gain new denial evidence before use. Eventu remains unchanged.
