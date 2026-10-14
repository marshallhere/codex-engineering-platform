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
watchdog interruption/recovery, resource exhaustion, durable UID quarantine/reuse or
privileged executable exclusion. Those requirements remain in
[native containment](NATIVE_CONTAINMENT.md). No container fallback or runtime fork grant
is applied. Slice C still requires qualified execution plus real rendered UI evidence.
