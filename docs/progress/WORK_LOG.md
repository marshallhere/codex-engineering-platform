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
### Real-project qualification phase started

- User authorized toolchain qualification and one isolated Eventu vertical.
  Work branch feat/native-toolchains-eventu starts at verified 619816c.
- Independent native lifecycle research rejects unrestricted fork grants: process
  groups do not contain setsid/double-fork descendants, and installed Darwin SDK
  and Apple XNU mark kqueue NOTE_TRACK unsupported. No boundary was weakened.
- Native Python/Node in-process probes and uv version discovery PASS. Exact-file
  binary bindings are frozen by hash; native Node cannot read adjacent protected
  files or spawn a child. A sacrificial outside executable cannot be hardlinked
  into writable project storage; its bytes and nlink remain unchanged.
- Added protected technology-neutral JSON CLI grading. Independent review found
  pre-grading output redaction could conceal token-shaped leaks. Trusted grading
  now sees raw bounded output first; persisted/broker outputs remain sanitized.
  Truncation and missing execution-limit flags fail cases. Regression retains
  both a synthetic leak and its sanitized failed evidence.
- Eventu current checkout has existing dirty work and a non-develop branch. It is
  preserved; the isolated private candidate archives exact origin 5ef7d53 and adds
  only scoped OpenSpec before worker execution. Its baseline 34 tests and 22-skill
  bundle checks PASS, distinct from current dirty-source checks. Ten protected
  invalid-scope cases fail as intended; five valid/default/recovery controls pass.
  A protected compile case brings final policy to 16 cases across all gate kinds.
- Private pack and policy remain outside the worker. No MCP/account bindings or
  private Eventu source were copied into the public platform repository. A stale
  Sentry paragraph in Eventu README remains an unrelated documented inconsistency;
  this slice performs no provider or scope-activation actions in the real workspace.
### Strict grading review closure

- Restricted root review found missing truncation metadata defaulted to false.
  Required explicit boolean timed_out, output_exceeded and output_truncated flags;
  added missing/invalid-flag regressions. Review retry PASS with unchanged runtime.
- First pilot was cancelled during final review before runtime correction; its
  artifacts remain private and are not completion evidence. Fresh pilot uses the
  corrected frozen runtime and original failing source snapshot.
- Current platform suite 157 PASS; original prototype57 PASS. Pinned Ruff PASS,
  static gate retains15 reviewed LOW findings, no HIGH/MEDIUM or scanner errors;
  strict validation now covers all OpenSpec changes, dependency audit remains clean.
- Native Go version discovery PASS; Go subprocess/build execution remains blocked.
  Source package includes public evidence JSON; final package/source matching and
  accepted Eventu proof remain pending at this checkpoint.
### Qualified real-project CLI milestone

- Implementation d53c5c5 passed public Linux/macOS CI run38577104873, including
  native exact-file binding, hardlink and Node fork-denial regressions.
- Fresh Eventu pilot ACCEPTED on the corrected runtime: four Codex phases,
  281.444 charged seconds within900 seconds, all18 externally owned cases PASS,
  final independent review PASS, immutable snapshot and idempotent acceptance verified.
- Only src/eventu_tooling/setup.py changed. Unknown/non-string/falsy persisted
  scopes are rejected before planning/apply, explicit valid recovery is preserved,
  and minimal older configuration remains compatible. Original34 tests and22-skill
  integrity checks PASS in a fresh copy of attested files, temporary secret-minimal
  environment and isolated Git configuration. The initial isolated direct-script
  command failed sibling imports; corrected bootstrap retained Python isolation.
  This functional verification is not general fork-capable worker qualification.
- Original Eventu HEAD/branch and all30 recorded dirty-file hashes unchanged.
  Private patch and full evidence retained under .local/eventu-vertical-prep/final;
  no source or private provider bindings were published, applied or merged.
- Sanitized completion proof: docs/evidence/real-project-cli.json. Runtime frozen
  bytes match live acceptance. Historical first pilot remains CANCELLED and its
  evidence is retained rather than substituted for the accepted run.
- Distribution passed171 packaging checks plus9 installed-module/CLI checks,
  and236 exact-source comparisons at implementation commit. Final documentation
  package rebuild/install is pending. Platform157 +prototype57 tests PASS; static
  findings remain15 reviewed LOW, no material findings. All OpenSpec changes strict
  PASS, dependency audit clean, publication scan PASS.
- Scoped real-project tasks checked. General descendant-safe native subprocesses,
  full framework builds, broader SDK attestation, UI/Storybook, reviewed-memory
  automation and remote integration still require separate qualification.

## 2026-10-14 — native UID experiments and Eventu reconciliation

### Scope and implemented boundary

`feat/native-uid-containment` began at `5f2d44e`. Experimental code lives outside
`src/cep`; the installable runtime and its no-fork policy are unchanged. OpenSpec
`native-uid-experiments` defines the limited evidence contract. No helper, login
account, daemon, global permission rule or production resource was installed.

Implemented checked Darwin libproc inventory, immutable birth/credential records,
a bounded POSIX kernel-group query, unused UID/GID selection, irreversible privilege
drop, hard process/file/core limits, and a root-owned exclusive CI lease. Cleanup
signals originate only from the permanently dropped UID sidecar. The root parent
observes/reaps; it never signals arbitrary PIDs. Fixtures are fixed and finite.
Developer-host `--qualify` refuses before privileged work.

Complete inventory of the development Mac's current user fails closed on existing
zombies whose birth metadata is unreadable. The diagnostic is retained in the
ignored `native-uid-current-inventory.json`; it is never treated as empty membership.
Actual own-process ABI, unused-UID inventory and kernel-group inspection pass.

### Independent review and repair evidence

Separate restricted Codex root sessions reviewed the experimental code read-only.
One malformed phase response was rejected by the transport. Another review overlapped
specialist edits and failed its unchanged-hash check; neither became final evidence.
A medium static finding about the lease's public temporary parent was resolved by
moving it beneath root-owned `/private/var/run` with no-follow/owner/mode/link checks.
Final native Bandit reports zero findings and errors; CI independently enforces this.

Reviews caught genuine false-pass and finalization defects: readiness and diagnostic
pipes were shared; detached-child errors could be ignored; inventory/wait failures
could bypass diagnostics and descriptor closure. Repairs use separate bounded pipes,
reject every worker/cleaner diagnostic, require expected exit statuses, and preserve
bounded reaping/closure even when membership remains unknown. New regressions cover
these paths. The concurrent fixture requires eight children before readiness and
at least nine observed processes. No assertion or security control was removed.

Darwin's account-directory `getgroups` extension fails for anonymous numeric UIDs.
Apple's libc/kernel sources and actual CI diagnostics established the cause. The
replacement reads the standard libSystem POSIX symbol with checked ABI/count/capacity,
retains GID 0, and requires exactly the fixture's primary group. Real/effective UID/GID
must match, all root-restoration attempts must be denied, and existing directory-service
UIDs/GIDs are excluded. Empty, duplicate and foreign groups fail.

Final restricted reviews (`review-native-uid-repair-final`, `kernel-groups`, `prereap`,
`sleep-path`) pass with their reviewed hashes unchanged. They cover only fixed disposable
experiments, not arbitrary workloads or production containment.

### Actual disposable macOS CI attempts

| Run | Source | Outcome and correction |
| --- | --- | --- |
| 38584212113 | 14d23c5 | Staging failed before fixtures: ordinary-shell glob cannot enter root-only directory. Use explicit filenames; retain failed artifact; keep mode 0700. |
| 38584608922 | 1fd108d | UID execution failed closed; initial diagnostics were insufficient. Add bounded diagnostic channels and real statuses. |
| 38586940156 | 4c81976 | Worker/cleaner EINVAL; final domain empty. Add operation-specific error labels. |
| 38587469091 | a8476e4 | Unlabelled post-setup EINVAL exposed the account-directory group lookup. Replace it with actual kernel credentials. |
| 38588737261 | 2781867 | Drop/cleanup succeeded, but initial inventory saw the deliberately exited direct parent as an unreaped zombie. Reap our own child before discovery. |
| 38589828765 | 0b0b05d | Detached fixture completed; posix_spawn rejected incorrect `/usr/bin/sleep` path. Verify/use macOS `/bin/sleep`; preserve partial case evidence. |
| 38591031224 | cfdea117 | All three fixed cases pass with zero survivors and zero diagnostic/inventory errors. |

Failed logs/artifacts remain ignored and preserved. A private negative control removing
only the five-line pre-discovery reap reproduces the zombie-observer regression; its
failure log is retained. An earlier wrong-cwd command did not execute and is excluded.

Successful run `38591031224` observed one detached process, two posix_spawn processes,
and ten during continued bounded forking. Cleaner exits were 0; worker statuses were
0/9/9 as required. Elapsed times were 0.171/0.228/0.475 seconds. The public evidence JSON
binds source `cfdea117fdcbf812aab584e4010262aa4aa729fd`, artifact hash and individual cases.
`production_qualified` remains false. Standard push `38591031006` and PR `38591037219`
contracts/native-boundary checks pass. Draft PR #2 is stacked on #1; neither is merged.

Final local gates: 179 platform tests and 14 + 43 original prototype tests pass;
22 targeted experimental tests pass; Ruff and strict OpenSpec pass; npm audit reports
zero vulnerabilities; publication scans pass; distribution verification reports 171
checks. Exact final source is also checked by clean-clone CI. No shipping runtime bytes
or execution capability changed. Only the narrowly defined experimental OpenSpec tasks
are complete. Watchdog durability, fork barriers, UID quarantine/reuse, inherited
filesystem/network restrictions, executable authority and resource exhaustion remain
unqualified; see `docs/NATIVE_CONTAINMENT.md`.

### Eventu: verified fix applied on the owner-selected branch

Private reconciliation preserved the newer `all` default and local overlays. Review
found malformed declaration handling (string substring membership and null fallback);
added four regressions and a closed declaration guard. Only a missing declaration
uses the legacy pinned fallback. Negative controls reproduced the defects. Existing
assertions were not weakened. The final reviewed patch SHA256 is
`33a970faabcd053ef268f0e793c0283fa60dab5770fc7a345a3e2692205eb769`.

The owner explicitly selected `docs/readiness-autonomous-execution` despite the repo's
`develop` instruction. Before applying, all 254 original source hashes/modes matched
the snapshot. Applied only the reviewed scope guard and new `test_scope_validation.py`.
Afterward, only `setup.py` changed among those 254 prior files; both changed/new files
match the reviewed candidate. Unrelated files, branch, HEAD and index are preserved.

Actual current-checkout verification: 106 tests pass on Python 3.14.7 and 3.13.9,
22 skills and full `bin/eventu verify` pass, and bootstrap check reports `all` with no
changes/conflicts. The 3.13 executable was resolved through the installed uv-managed
interpreter after a PATH-only command failed. No provider, global configuration or
application deployment changed. No mixed commit was created: older uncommitted setup
changes are not ours and the scope patch cannot apply to index HEAD without those
prerequisites. Private integration evidence records the exact delta. The unrelated
newer readiness test's sibling-docs fixture dependency remains a standalone CI gap.

### Next approved work: actual fixed toolchain builds

New branch `feat/native-toolchain-build-probes` starts at `ee49fae`. OpenSpec
`native-toolchain-build-experiments` defines protected offline uv/Python, Node child-build
and Go stdlib-build receipts using pinned, immutable SDK trees and disposable UIDs.
Specialists own disjoint new probe/test and workflow files. Passing fixed builds will
establish compatibility only; it cannot activate general forks or fulfill Slice C's
security/rendered acceptance requirements. No fallback or host installation is planned.


The fixed probes and workflow are now implemented. Archive review exposed alias-copy
amplification and implicit-directory conflicts: six of 21 negative controls failed
before repair, all 21 pass afterward, and four official ARM64 archives pass revised
preflight without privileged local execution. Worker review exposed dispatch after
budget/failure and truncated output: deadlines now precede spawn, failures stop future
commands, and complete output is retained within the 64 KiB bound. A real ordinary-UID
subprocess regression retains >12 KiB of leading junk and rejects its receipt.

Independent specialist review passes for the frozen probe/workflow hashes; 11 focused
probe tests and all 190 platform + 14 + 43 original tests pass. Ruff passes, experimental
Bandit has zero findings/suppressions, the unchanged core's 15 reviewed LOW findings pass
its gate, strict OpenSpec validates all four changes, and npm audit reports zero
vulnerabilities. Separate restricted Codex root review and actual disposable CI builds
are still pending; none of these local checks establishes build or backend qualification.


Restricted root review `review-native-build-01` failed on an additional pipe-lifetime
bug: direct-child exit could stop capture before descendant-held streams reached EOF.
The failure receipt and reviewed hashes are preserved. Repair/regression is underway;
no privileged CI execution or completion claim occurred on the rejected source.
Distribution build and artifact verification passed 171 checks for that pre-repair
source; a changed probe requires renewed verification.


The rejected pipe behavior is repaired in both command-output and parent-report
observers: direct-child exit no longer ends capture before EOF. Bounded waits retain
delayed descendant stderr and reject the command receipt; a mocked parent-report test
retains the delayed final frame. All 13 probe tests pass. The changed experimental code
again has zero Bandit findings/suppressions and passes Ruff. Restricted root re-review
`review-native-build-02` is running against frozen hashes. Archive controls are being
made part of the portable standard test suite rather than only private evidence.


Restricted root re-review `review-native-build-02` passes with all reviewed files
unchanged. Probe SHA256 `2fc03eb5c433a65e3699f8a0ef1f3dbd895c8bb15385416c38ef7f71f48506e1`
and workflow SHA256 `3c37806497826b892ede100b80c13dbb3c0e9dec06fe84e5ed543f956030b32f`
are bound in the private review summary. Eleven no-fork tests ran in that restricted
review; the two actual subprocess regressions were inspected and passed separately
under the ordinary developer UID. Full local regression now passes 192 platform tests.
All four embedded workflow Python blocks parse for system Python 3.9. Actual build
compatibility remains unclaimed until disposable CI receipts are inspected.


### Actual fixed-build receipts

Source `a9ef861d18289e0bf1e87f592b9f09be50c7f224` was published on the feature branch
and draft stacked PR #3. Disposable ARM64 CI `38596959945` and standard contracts/native
boundary CI `38596959599` pass. Inspected downloaded raw reports: all Python/uv, Node
and Go recipes pass; worker/cleaner statuses, survivors and error counts are all 0;
there are no diagnostics, timeouts or output overflows. Root-only staging cleanup passes.
Verified each retained artifact's byte count and SHA256 against the raw receipt.
Public evidence binds the source, reviewed files, archive/SDK identities and results.
No local SDK/root execution or runtime fork grant occurred.

The old premature-capture exit was restored only in an in-memory ordinary-UID negative
control: the delayed-descendant regression fails as expected (1 failure, 0 errors).
The repaired 13 probe controls pass. Twenty-one portable archive tests now pass on
Python 3.13/3.14 and parse on 3.11. The source distribution must include their exact
workflow input; added its explicit manifest entry and an outside-checkout archive-test
gate. Packaging and final portable CI verification are pending on this follow-up.


Follow-up restricted root reviews of the portable archive tests/public evidence and
packaging diff pass with their reviewed hashes unchanged. Final local gates: 213
platform tests + 57 original tests pass, Ruff passes, all four strict OpenSpec changes
pass, npm audit is clean, and publication scans of history/index/worktree pass.
Distribution verification now passes 174 checks, including all 21 archive controls
from the extracted sdist outside this checkout. Portable Ubuntu CI remains pending;
OpenSpec final review/check task remains open until that exact revision passes.


Final portable source `a007f0da390c06e48d4698c7b5506deed6c6af3c` passes push CI
`38597609994` and PR CI `38597617265`, including Ubuntu's full 213-test suite,
57 historical tests, zero experimental security findings, package build and all 174
outside-checkout verification checks. macOS shipping native-boundary tests also pass.
The actual SDK probe/workflow bytes are unchanged from successful source `a9ef861`.
Only the four narrowly scoped experimental OpenSpec tasks are marked complete.
A stale pending label in the older UID evidence mapping is corrected to its already
verified run; no evidence is discarded. No shipping runtime code changed.

Next required boundary work remains independently enforced inherited sandbox rules,
privileged executable exclusion, durable independent watchdog/recovery and UID
quarantine/reuse, followed by adversarial resource and real framework/UI verification.
Positive fixed SDK builds do not satisfy these requirements. No fork-enabled CEP job,
Slice C, host installation, project merge or deployment is claimed complete.

### Next qualification slice: UID quarantine after controller interruption

Branch `feat/native-uid-quarantine` starts at the reviewed native build milestone
`a5247d1`. Read-only audit found a concrete gap in both privileged experiments: the
root orchestrator forks a worker before privilege drop and only starts UID cleanup in
its own `finally` block. SIGKILL between those points releases the flock and can leave
an unobserved worker; process inventory may therefore let a later invocation choose
the same numeric UID. The ordinary runtime already has a separate launch barrier and
watchdog for its single process-group commands, but detached UID fixture descendants
need a durable domain reservation of their own.

The scoped implementation adds a private persistent UID reservation journal, records
its entry before every worker fork, skips stale records on allocation, and releases only
after verified child/cleaner success and two distinct empty inventories. It does not
claim automatic orphan termination or release stale records. A disposable macOS fault
injection will kill an orchestrator around its fork/drop boundary and prove a subsequent
allocation cannot reuse its reserved UID. Shipping runtime behavior remains unchanged.

Implementation checkpoint: durable UID quarantine

The first implementation pass adds `native/uid_journal.py`, root-owned journal
validation, reservation before both privileged probe paths, stale reservation
exclusion, and nonce-bound release after child/cleaner receipts and two distinct
fresh empty inventories. The journal never auto-recovers a stale reservation.
The controller interruption regression leaves a detached child alive after SIGKILL
and confirms its UID remains reserved. The native macOS workflow now stages that
regression with the privileged probe code and runs it under root before the fixed
UID experiment, retaining both outputs. This protected macOS CI run has not yet
executed for this branch and remains mandatory before marking the change complete.

Local evidence so far: 229 platform tests and 38 UID-focused tests pass; Ruff 0.13.3
passes; strict OpenSpec validation passes all five changes; npm audit reports zero
high-severity vulnerabilities; Bandit reports zero native findings; source/wheel
build and isolated packaging verification pass all 174 checks; publication scan
passes with no findings. The separate restricted Codex review returns PASS with no
blocking findings and confirms the remaining limit: general sandbox/runtime and
production recovery are still unqualified. No root probe was run locally.

CI iteration note: the first macOS run caught a stale staged-path reference after the
workflow moved its protected source files into a `native/` subdirectory for the
isolated test imports. The controller-interruption regression passed its step; the
fixed probe step failed to open the former root-level path before executing. The
workflow now points at the staged `native/uid_probe.py`. No test or guard was changed
to mask the failure; a new macOS run is required to verify the repair.
A second macOS CI iteration passed the new root-run controller-interruption regression
and reached the UID probe. The root probe guard rejected the newly nested `native/`
staging directory because `mkdir` left it at mode 0755; the probe failed closed before
running any fixture. The workflow now explicitly makes all staged subdirectories 0700.
This preserves the guard and tightens staging; another disposable macOS run is required.
