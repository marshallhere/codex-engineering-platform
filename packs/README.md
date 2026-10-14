# Technology packs v1

The editor-facing schema is `plugin/packs/schema.v1.json`; the runtime additionally
checks path containment, unique identifiers and executable restrictions.

The shipped Python and Go manifests live in `plugin/packs/` so the plugin stays
self-contained. Put external pack directories anywhere; `discover_packs(root,
project)` accepts a catalog directory or a single pack directory. The core does
not branch on technology. Loading/discovery never executes a command or grants
permissions. A detected pack is only a candidate until its ID is selected in
`engineering-platform.toml` and its actual commands pass qualification.
List external catalogs in `pack_paths = ["technology-packs"]` and select their
IDs in `packs`. A pack can supply agent profiles as `agents/<role>.toml`; duplicate
pack IDs and conflicting role definitions are rejected. Profile installation is
selective and uses the same ownership/rollback rules as bundled profiles.

Each `pack.json` is a strict JSON object: `schema_version` (1), lowercase `id`,
semantic `version`, `description`, `detect.any_files`, `toolchains`, `commands`,
`roles`, and `required_capabilities`. Toolchains declare `name`,
`version_command` argv, and `version_constraint`. Commands declare unique `id`,
`action` (`test`, `lint`, `typecheck`, `build`, `security`, `format-check`), `argv`,
relative `cwd`, `timeout_seconds` (1–3600), and boolean `required`.

Executables are resolved by the qualified environment; command arrays are never
shell strings. Shell/privilege wrappers, absolute paths, traversal, duplicate
keys and unknown fields are rejected. These checks validate format, not the
trustworthiness of commands: a test runner can execute arbitrary project code.
Required capabilities describe needs and never grant access. Keep grants and
mandatory gate policy outside worker scope.

Python's recipe requires the portable `python3` command to resolve to a qualified
3.11+ interpreter and a real `tests/` suite. Go follows `go.mod`; provisioning and
network access are separate approvals. Projects may supply a new pack with their
own validated commands instead of changing the core scheduler.
