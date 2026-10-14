## ADDED Requirements

### Requirement: CEP-SDK-FIXED actual offline build receipts
The experiment SHALL execute immutable fixed uv/Python, Node child-build and Go
stdlib build recipes, compare real output/artifacts and retain per-case evidence.
Version discovery alone SHALL NOT establish positive build compatibility.
#### Scenario: Missing or failed build
- **WHEN** a compiler exits unsuccessfully or a required artifact/output is absent
- **THEN** its case fails and earlier passing evidence remains available

### Requirement: CEP-SDK-AUTHORITY pinned immutable SDKs
SDK archives SHALL be pinned and digest-verified before extraction. Their staged
content SHALL be root-owned, bounded, read-only and tree-digest-bound; writable,
set-ID, hardlink and outbound symlink authority SHALL be rejected.
#### Scenario: Changed SDK
- **WHEN** staged content, metadata or executable selection changes
- **THEN** the experiment blocks before execution or rejects its evidence

### Requirement: CEP-SDK-DISPOSABLE independent UID execution
Privileged probes SHALL run only through the explicitly selected disposable CI
workflow. UID/GID/groups SHALL drop before SDK execution; each case SHALL have fresh
scratch/cache, finite execution and independent membership cleanup.
#### Scenario: Ambiguous teardown
- **WHEN** child diagnostics, unknown final membership or survivors remain
- **THEN** the case fails without UID reuse or production qualification

### Requirement: CEP-SDK-NO-PROMOTION compatibility scope
Positive fixed builds SHALL NOT activate a runtime backend, permit arbitrary project
execution or claim watchdog, filesystem/network isolation, resource-exhaustion,
privileged-executable or UID-reuse qualification. The no-fork backend SHALL remain.
#### Scenario: Successful build receipts
- **WHEN** all fixed recipes pass
- **THEN** evidence still reports production qualification false and lists gaps
