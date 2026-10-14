## ADDED Requirements

### Requirement: CEP-SETUP portable project integration
The platform SHALL selectively install project integration, preserve user edits,
detect conflicts, support dry run and rollback, and never export credentials.
#### Scenario: Existing configuration
- **WHEN** a project already has instructions and tool settings
- **THEN** onboarding preserves them and reports conflicting managed content

### Requirement: CEP-PACK technology-independent extension
The core SHALL load versioned technology packs without framework branches in its scheduler.
#### Scenario: External pack
- **WHEN** an independently supplied compatible pack passes conformance
- **THEN** its declared tools and commands are available without editing core code

### Requirement: CEP-JOB durable bounded work
Jobs SHALL reserve attempts before execution, enforce explicit active-time budgets,
isolate concurrent resources and recover interruptions without claiming completion.
#### Scenario: Interrupted attempt
- **WHEN** the controller exits during an attempt
- **THEN** restart records incomplete work and revalidates before continuing

### Requirement: CEP-BOUNDARY independent execution restrictions
Worker, reviewer and gate processes SHALL have verified restrictions and no ability
to overwrite control policy, acceptance fixtures or state.
#### Scenario: Failed isolation
- **WHEN** an escape probe succeeds or the backend is unsupported
- **THEN** dependent live execution is blocked with retained evidence

#### Scenario: Administrative aliases and owner instructions
- **WHEN** a worker writes through case aliases or attempts to change agent instructions
- **THEN** the broker and native boundary deny the write and frozen instruction evidence detects additions or changes

### Requirement: CEP-EVIDENCE candidate-bound completion
Completion SHALL require frozen requirements, all mandatory gates and independent
review on the same immutable candidate. Changed policy or content invalidates evidence.
#### Scenario: Tampered candidate
- **WHEN** content changes after checks
- **THEN** previous passing results cannot authorize acceptance or merge

### Requirement: CEP-LOOP real repair and review
The runtime SHALL support implementation, verification, repair, independent review,
polish and final revalidation, with finite retries and evidence-linked findings.
#### Scenario: Failing acceptance
- **WHEN** an acceptance test detects a defect
- **THEN** the failure becomes repair input and cannot be marked passed without reexecution
