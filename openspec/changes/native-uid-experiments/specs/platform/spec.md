## ADDED Requirements

### Requirement: CEP-UID-EXPERIMENT disposable authority
Privileged UID experiments SHALL refuse execution outside explicitly selected
GitHub-hosted disposable macOS runners. The experiment SHALL use an unused numeric
UID and permanently drop supplementary groups and real/effective UID before any
fixture forks or signals. It SHALL NOT install accounts, services or permission rules.
#### Scenario: Developer machine
- **WHEN** qualification is requested on an ordinary developer machine
- **THEN** execution fails before UID changes, process signals or fixture creation

### Requirement: CEP-UID-INVENTORY checked native membership
Native UID inventory SHALL validate ABI sizes, bounded result capacity and every
returned process identity. Unsupported platforms and ambiguous enumeration SHALL
fail closed rather than report an empty domain.
#### Scenario: Truncated inventory
- **WHEN** native enumeration reaches buffer capacity or returns malformed data
- **THEN** qualification fails without claiming zero survivors

### Requirement: CEP-UID-EVIDENCE bounded detached cleanup experiments
The experiment SHALL exercise detached descendants and bounded concurrent forking,
retain case outcomes and verify final UID emptiness. Cleanup signals SHALL originate
from the permanently unprivileged fixture UID, never root, to avoid signalling an
unrelated process after PID reuse.
#### Scenario: Detached descendant
- **WHEN** the immediate child exits and descendants change session or close pipes
- **THEN** membership discovery does not depend on ancestry or inherited output pipes

### Requirement: CEP-UID-NO-PROMOTION experimental results
The shipping no-fork runner SHALL remain unchanged. Passing fixture experiments
SHALL NOT establish build qualification, strict deadline containment, filesystem or
network isolation, watchdog durability, or permission to activate this backend.
#### Scenario: Passing experimental probes
- **WHEN** synthetic UID cleanup probes pass
- **THEN** the report still marks production qualification blocked
