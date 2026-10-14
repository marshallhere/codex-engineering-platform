# Portable local setup

CEP mirrors capability behavior, not a byte-for-byte snapshot of a developer's
Mac. The shareable core contains its own workflows, specialist profiles, project
installer and technology packs. `config/capabilities.json` records sanitized
metadata about the local sources inspected during implementation. It does not
activate integrations, prove provider access or grant redistribution rights.

## What belongs in the repository

| Disposition | Meaning |
| --- | --- |
| `bundled` | CEP-owned material distributed with this repository. |
| `reference` | External capability to obtain separately from its owner. |
| `runtime-provided` | A skill supplied by the installed Codex runtime. |
| `private-binding` | A user's machine, project or account configuration, kept outside the public core. |
| `unavailable` | Metadata could not be safely inspected or the capability has no usable transport. |

Third-party plugin caches and private project skills are never copied into the
core by the inventory. A manifest's license declaration is evidence to review,
not permission inferred by CEP. Unknown licenses mean redistribution is not
authorized. CEP's MIT license does not relicense dependencies or external skills.

Each user obtains Codex and their chosen external plugins independently, then
configures their own private account bindings. Known package versions are kept
as references. Missing versions require qualification before adoption; the
inventory does not choose a latest release automatically.

## MCP capabilities

The inspected configuration declares these optional capabilities. Entries from
the global and workspace layers retain separate source labels, so duplicate
names do not imply two working connections.

| Names | Purpose and binding |
| --- | --- |
| `github` | Repository access using the user's own connection. |
| `node_repl`, `computer-use` | Local runtime and computer interaction. |
| `cloudflare-api`, `terraform` | Infrastructure tooling with private accounts and scopes. |
| `stripe`, `resend` | Provider tooling with independently verified account and environment. |
| `chrome-devtools`, `next-devtools` | Existing browser and project development tooling. |
| `context7`, `better-auth` | Documentation and framework support. |
| `grafana`, `sentry` | Observability with private organization and project bindings. |
| `database-toolbox` | Database tooling with private connection configuration. |

The public catalog defaults every MCP and external plugin to disabled. Select
capabilities per project and verify the required connection before using it.
Configured, installed, authenticated and qualified are separate states. This
inventory establishes metadata only. It never calls a provider, launches an MCP,
opens a database or verifies delivery.

## Inspect without exporting private configuration

The Python API accepts explicit source paths and returns JSON-safe metadata:

```python
from pathlib import Path
from cep.inventory import inventory

home = Path.home()
workspace = Path("/path/to/workspace")
report = inventory(
    config_paths=[home / ".codex/config.toml", workspace / ".codex/config.toml"],
    skill_roots=[home / ".agents/skills", home / ".codex/skills/.system",
                 workspace / ".agents/skills"],
    plugin_roots=[home / ".codex/plugins/cache"],
)
```

The checked-in catalog uses that ordering: `config-1` is the global layer,
`config-2` the workspace layer; `skill-root-1` is user skills, `skill-root-2`
runtime skills, and `skill-root-3` workspace skills. `plugin-root-1` is the local
plugin cache. Source labels intentionally omit machine paths.

The inventory reads only Codex configuration, skill entrypoints, adjacent agent
profiles, plugin manifests and license markers. Credential stores, environment
files, sessions and memory directories are not inputs. Results contain MCP
names, transport types, allowlisted public endpoint addresses, environment
variable **names**, safe package references, skill hashes, plugin identities and
versions, and license provenance. Header values, environment values, arbitrary
launcher arguments, skill bodies and developer instructions are omitted.
Private endpoints become `<private-endpoint>`; unknown executables become
`<local-executable>`. An allowlisted public endpoint is reconstructed without
query strings, fragments, credentials or account-specific path components.

Symlink skill entries are recorded as unavailable without following their
targets. Source owners can supply an explicit trusted source directory for a
separate inventory. Symlink targets and absolute source paths are never exported.
Unreadable or bounded traversal failures produce generic warnings; warnings
must be resolved before claiming a complete inventory.

Local agent-profile metadata is separate from CEP's bundled specialist profiles.
Finding no adjacent local profiles does not mean Codex has no built-in agents.
Likewise a cached plugin manifest does not prove that the plugin is enabled in
the current session.

For Eventu, `eventu-tooling` remains the portable source of workspace skills,
helpers and MCP scopes. CEP inspects that workspace without transferring its
provider identifiers, private endpoints, secrets or policy ownership into the
public core. Use the project's own bootstrap checks when maintaining its setup.

Project activation uses the reversible CEP installer. Review its dry run before
applying it; resolve conflicts instead of overwriting local configuration. Local
setup metadata does not satisfy runtime security qualification. A failed native
preflight blocks worker launch and must not be bypassed.

## Publication audit

Stage all intended release files, then run from the repository root:

```sh
python3.14 scripts/check_publication.py .
```

The script scans every reachable Git history object, the index and current
tracked file contents. A credential removed in a later commit still blocks
publication. Commit and annotated-tag text are scanned too. Deleted tracked
files remain covered through the index and history. Worktree symlinks are scanned
as link text, never followed. Shallow history, unmerged index entries, submodules,
missing objects and files over the scan bound block a passing result.

Findings report only scope, object identifier, safe filename, line and finding
kind. Matching values are never printed. Sensitive filenames are redacted. The
scanner recognizes private keys, several provider credential formats, bearer
tokens, JWTs, credential-bearing URLs, quoted secret assignments, personal home
paths, and private or link-local IPv4 addresses. It has no blanket test-file
exception.

The narrow documented example exceptions are:

- RFC 5737 documentation addresses.
- Home-path example names `me`, `user`, `example` and `username`.
- Angle-bracket placeholders, uppercase environment substitutions and the exact
  placeholder words listed in `_PLACEHOLDERS` in the scanner.
- This exact dummy address, only on a line containing the shown marker:
  `10.0.0.1 # publication: dummy-ip`.

Do not annotate real infrastructure as dummy data. Replace private example
addresses with documentation addresses instead. If a real credential is found,
revoke it and remove it from all relevant history before publishing; deleting
only the current file is insufficient.

This bounded pattern scanner cannot identify every possible secret. Untracked
files, ignored files and unreachable Git objects are outside its coverage.
Inspect the staged release set, provenance and redistribution rights separately.
A passing report is evidence for the stated patterns and Git coverage, not a
claim that every local capability is installed, authorized or secure.
