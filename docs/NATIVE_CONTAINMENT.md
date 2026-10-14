# Native containment qualification

The installable runtime currently qualifies only its no-fork Seatbelt backend.
`native/` is a separate experiment, with fixed finite disposable fixtures. Passing
its tests or CI cannot authorize arbitrary workloads or produce live job acceptance.

## Evidence required before fork-dependent builds

| Boundary | Required adversarial evidence | Current status |
| --- | --- | --- |
| Process membership | Dedicated UID/GID absent from accounts and live processes; real/effective/saved identities stay fixed through fork/exec | Read-only ABI/empty-UID checks pass; full execution experimental |
| Launch registration | Root-owned lease and independent watchdog exist before releasing untrusted code; controller failure before/after release cannot orphan it | Not implemented |
| Teardown | Session/group changes, closed pipes, parent exit, posix_spawn, continuing forks and in-flight fork race; verified zero survivors before reuse | Three fixed CI probes pass; atomic fork barrier unproved |
| PID reuse | Cleanup cannot signal a different identity after PID reuse; ambiguous observations block | Same-UID signal authorization designed; synthetic only |
| UID reuse | Durable quarantine after uncertain cleanup; independent recovery before reuse | Invocation-local exclusion only |
| Filesystem | Inherited no-follow/case-aware protected policy; project writable, control/acceptance/auth/toolchain immutable; hardlinks and aliases blocked | Shipping no-fork backend qualified; UID backend unproved |
| Network/credentials | Descendants cannot access network, keychains, SSH/password-manager agents, provider secrets or personal configuration | Shipping no-fork backend qualified; UID backend unproved |
| Executable authority | Exact or immutable reviewed SDK bindings; privileged executables, identity changes and toolchain tampering rejected | Shipping exact-file bindings exist; fork/SDK authority unproved |
| Resource budgets | Hard process/file/output limits, bounded CPU/memory/disk, cancellation/deadline and watchdog-failure recovery | Fixed synthetic limits only |
| Real tools | Protected, offline uv/Python subprocess, Node child build, Go stdlib build and negative escape probes under the same final boundary | Discovery/in-process probes only |
| UI | Next.js/Storybook builds, browser isolation, a11y/visual protected artifacts and component-reuse acceptance | Slice C blocked on execution qualification |

Do not substitute ancestry polling or successful tool version output for these
contracts. Do not enable forks in the shipping profile or add a container fallback.
A developer-machine privileged installation needs a concrete reviewed helper bundle
and authorization for its host changes; these CI experiments install nothing.

Current-user inventory on the development Mac fails closed when existing zombies
lack readable birth metadata. This is preserved as failed evidence, never interpreted
as empty membership. Fresh numeric fixture UIDs avoid existing user processes but
still need independent lifecycle and reuse proofs.

## Eventu integration

The accepted older-source pilot is distinct from the newer dirty-source reconciliation.
The owner selected the existing branch despite its `develop` instruction. The verified
scope guard and regression tests are applied there; defaults, local overlays and all
unrelated working changes are preserved. Its106tests pass on both installed supported
Python versions,22skills/fullverify pass and bootstrap check reports all/no drift.
No mixed commit was created: the existing dirty setup changes predate this patch.
No readiness, provider-access or production claim follows from tooling unit tests.
