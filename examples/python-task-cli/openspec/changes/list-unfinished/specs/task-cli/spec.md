## ADDED Requirements

### Requirement: DEMO-LIST unfinished inventory
The command SHALL accept --root and --file and emit only unfinished tasks, preserving
input order and the fields of each task, as a JSON object with a tasks array.
Each task SHALL have a nonempty string id, string title and boolean done.
#### Scenario: Mixed inventory
- **WHEN** an inventory has finished and unfinished tasks
- **THEN** output contains exactly the unfinished tasks and exits zero
#### Scenario: Empty result
- **WHEN** all tasks are done or the inventory is empty
- **THEN** output is {"tasks": []} and exits zero

### Requirement: DEMO-INPUT invalid input
The command SHALL reject missing files, malformed JSON and invalid task shapes,
with nonzero exit status and a concise error on stderr without a traceback or
the input contents. Valid input SHALL be an object containing a tasks array.
#### Scenario: Invalid inventory
- **WHEN** JSON is malformed or done is not a boolean
- **THEN** the command exits nonzero without modifying input files

### Requirement: DEMO-BOUNDARY root containment
The command SHALL reject absolute --file paths, parent traversal and symlinks
resolving outside --root. The root SHALL be an existing directory. Input files
SHALL remain unchanged. The command SHALL not access external services.
#### Scenario: Escaping file
- **WHEN** --file refers outside the root through traversal or a symlink
- **THEN** the command exits nonzero without emitting the outside file contents
