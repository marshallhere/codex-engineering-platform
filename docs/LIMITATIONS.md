# Qualification status and remaining work

The acceptance boundary is trusted local controller code, not model instructions.
Workers have no control-state API. Protected tests, OpenSpec and runtime sources
are frozen. Fresh reviewer sessions use read-only permissions. Operator-owned
acceptance policies remain trusted input; weak policies cannot establish meaningful
acceptance.

| Capability | Current status |
| --- | --- |
| Reversible selective project setup | Implemented; conflict, rollback and preservation tests |
| Technology-neutral pack loading | Implemented; external pack tests, Python/Go fixtures |
| Python live loop | Demonstrated; final-build qualification recorded separately |
| Native command isolation | macOS no-fork Seatbelt; filesystem, TCP, Unix socket and fork probes |
| Jobs and lifecycle | Durable state, bounded reservations and watchdogs; fault tests |
| Integration | Serialized local eligibility assessment; no remote merge/push automation |
| Reviewed long-term memory | Workflows and historical utilities; automated promotion pending |
| Storybook, visual QA and accessibility | Required policy categories and skills; live UI adapter pending |
| Existing provider MCPs | Inventory only; project/account qualification required |
| Go autonomous workers | Pack, fixture and native version discovery tested; fork-dependent execution unqualified |
| Linux/Windows live workers | Unsupported; fail closed |

Worker project configuration accepts only the installer-owned CEP activation
table. Additional project MCPs, hooks and settings block until adapted. Native
shell tools are disabled. Dedicated broker commands execute without process-fork
permission, so many build tools cannot run yet. This boundary followed a failed
detached-process probe against the broader Codex sandbox; failed evidence remains
private. The complete native Codex tool surface requires adversarial live probes.

Generic candidate-run tests are not an independent grader: untrusted code can
exit before assertions or alter imported test behavior. Live acceptance supports the shipped demo contract and externally owned declarative
JSON CLI cases. Broader project execution and grading protocols fail closed until
qualified; see [real-project contracts](REAL_PROJECTS.md). Existing test namespaces are frozen,
including added package initializers and runner plugins.

OpenSpec is pinned to 0.17.2. The inspected 1.14.1 dependency tree had high-severity
advisories with no available registry fix at inspection. Strict validation and
a zero-advisory audit passed for the pin. Upgrade requires fresh compatibility
and security checks.

Public summaries omit prompts, machine paths, credentials and account bindings.
Raw live artifacts stay local and ignored. A passing publication scanner is
bounded evidence, not a guarantee of arbitrary-secret detection.

Subsequent slices must qualify chat/control MCP exposure, provider adapters,
integration against actual remote CI, human-reviewed memory promotion, rendered
design acceptance, and unattended multi-project lifecycle behavior.

Administrative, test and instruction protections compare path names without case
sensitivity. Native qualification covers case aliases of configuration, repository
and parent directories on macOS, including paths with spaces. Project agent roles
accept instruction/model fields only; authority overrides require qualification.

Exact-file executable bindings and external packs are content-bound to jobs. Python
and Node in-process work is verified; uv/Go version discovery does not authorize
subprocesses. Raw security output is checked before evidence redaction; truncated
or missing execution-limit outcomes fail protected cases. Full SDK/dependency
attestation and general native descendant containment remain pending.
