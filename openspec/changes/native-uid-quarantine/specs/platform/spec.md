## ADDED Requirements

### Requirement: CEP-UID-QUARANTINE durable pre-fork reservations
The disposable experiments SHALL create a private durable numeric UID reservation before forking any worker. Allocation SHALL exclude all active, stale, malformed or ambiguously read reservations, even when no process is visible under that UID.
#### Scenario: Controller interrupted before cleanup
- **WHEN** the controller is terminated after `fork` and reservation but before cleanup completes
- **THEN** a later allocation refuses or selects another UID; it SHALL NOT reuse the reserved identity

### Requirement: CEP-UID-RELEASE verified empty domain
A reservation SHALL be removed only after the worker and cleaner exit successfully and two consecutive checked UID inventories report empty membership. Inventory, status, journal or filesystem errors SHALL leave the UID quarantined.
#### Scenario: Ambiguous cleanup
- **WHEN** process inventory is unknown, cleanup fails or either child status is nonzero
- **THEN** the durable record remains and future allocations skip it

### Requirement: CEP-UID-NO-RECOVERY-CLAIM quarantine scope
The journal SHALL not claim to recover, signal or terminate orphan processes. Stale reservations remain unavailable until a separately reviewed recovery operation; positive experiments SHALL continue to mark production qualification false.
#### Scenario: Stale record after restart
- **WHEN** a prior run left a reservation record
- **THEN** allocation skips it without inferring that the UID is safe to release
