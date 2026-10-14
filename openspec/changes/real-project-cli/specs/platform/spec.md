## ADDED Requirements

### Requirement: CEP-TOOLS exact executable authority
The platform SHALL qualify supported in-process tool invocations, bind operator-selected
external executables by content digest and grant only exact-file read access.
#### Scenario: Changed tool
- **WHEN** a bound executable changes or belongs to the worker checkout
- **THEN** the job rejects it before worker execution
#### Scenario: Fork-dependent tool
- **WHEN** a tool requires unrestricted descendants
- **THEN** it remains blocked and version discovery cannot establish build qualification

### Requirement: CEP-JSON protected external CLI grading
The controller SHALL evaluate bounded declarative CLI cases outside worker ownership,
with requirement mappings, protected fixtures and finite per-invocation execution.
#### Scenario: Hidden leak
- **WHEN** raw child output contains a forbidden canary or capture is truncated
- **THEN** the security case fails before output is sanitized for retained evidence
#### Scenario: Candidate exits early
- **WHEN** a candidate exits successfully without the required output
- **THEN** its case fails regardless of candidate-owned test reports
#### Scenario: Mutable fixtures
- **WHEN** a case explicitly permits fixture writes
- **THEN** those writes remain in disposable execution scratch and requested nonmutation checks still apply

### Requirement: CEP-PACK-BIND selected pack evidence
An explicitly selected external technology pack SHALL remain validated and content-bound
through implementation and review without changing scheduler code for its technology.
#### Scenario: Pack edited during job
- **WHEN** selected pack content changes after submission
- **THEN** the frozen job cannot reuse prior evidence

### Requirement: CEP-EVENTU private isolated Eventu vertical
The platform SHALL implement and independently grade a real scoped Eventu tooling fix
in a frozen disposable repository, preserve the original dirty checkout and disclose
which exact source revision the evidence covers.
#### Scenario: Existing working changes
- **WHEN** Eventu contains uncommitted work
- **THEN** its files stay unchanged and acceptance does not claim to cover that work
