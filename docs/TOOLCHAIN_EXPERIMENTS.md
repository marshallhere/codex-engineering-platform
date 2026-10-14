# Fixed native build experiments

The shipping runtime still denies forks. Its `qualify-toolchains` command establishes
in-process compatibility and version discovery only. Separate scripts under `native/`
exercise fixed offline build fixtures on disposable macOS CI; they cannot accept jobs.

## Inputs and ownership

The dedicated workflow selects pinned Python 3.13.9, uv 0.9.9, Node 24.11.1 and Go
1.27.2 archives for its architecture. SHA256 verification precedes bounded extraction.
SDK trees are root-owned and read-only, with checked versions, executable selection and
full tree digests. Internal archive aliases become separate regular files; traversal,
case/normalization aliases, outbound links, set-ID files and extraction amplification
are rejected. This is integrity relative to reviewed pins, not publisher-signature proof.

Protected code, SDKs, immutable fixture sources and writable build scratch have distinct
owners/permissions. Each case permanently drops UID/GID/groups before any SDK executes.
HOME and caches are fresh. Fixed recipes use explicit offline settings; there are no
application credentials, provider operations or SDK installations on the developer Mac.

## Receipts and limits

The Python fixture uses uv to compile and execute real bytecode. The Node fixture runs
a real child process and emits an artifact. The Go fixture compiles stdlib-dependent
source and runs the resulting binary. The observer checks output and artifacts, retains
command outcomes and failures, verifies SDK/fixture integrity and drains the case UID.

Budgets, output limits and failures stop further dispatch. Unknown membership, child
errors or survivors block the experiment. Earlier passing receipts remain available if
a later case fails. Tests with mocks establish control behavior only; actual CI receipts
must establish build compatibility. Reports always include `production_qualified: false`.

No positive receipt qualifies arbitrary candidate code, inherited Seatbelt restrictions,
watchdog interruption/recovery, resource exhaustion or privileged executable exclusion.
The fixed probes do persist and honor reservations within the disposable runner, but do
not qualify orphan cleanup or production UID recovery. Those requirements remain in
[native containment](NATIVE_CONTAINMENT.md). No container fallback or runtime fork grant
is applied. Slice C still requires qualified execution plus real rendered UI evidence.


## Verified fixed-recipe result

[Disposable ARM64 run 38596959945](https://github.com/marshallhere/codex-engineering-platform/actions/runs/38596959945)
passed all three builds on source `a9ef861d18289e0bf1e87f592b9f09be50c7f224`.
Each worker and cleaner exited 0, with zero survivors, diagnostics or inventory errors;
staging cleanup also passed. The [public evidence summary](evidence/native-toolchain-build-experiments.json)
records source/file hashes, archive/SDK identities, outputs and verified artifact hashes.

Thirteen probe controls and 21 portable synthetic archive controls retain the reviewed
failure behavior. The latter run the workflow's exact extractor AST without privileged
staging or downloads, and scale the byte cap only in three tiny test fixtures.
Source distributions retain that workflow and run these controls outside the checkout.
This result establishes these fixed recipes on the observed ARM64 runner. General
execution and x86_64 build compatibility remain unqualified.
