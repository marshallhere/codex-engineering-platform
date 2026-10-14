# Qualified real-project CLI work

The controller supports two independent grading adapters: the historical shipped
Python demo and a technology-neutral declarative JSON CLI adapter. A private
Eventu tooling task is the first real-project proof. This does not qualify all
Eventu functionality, provider operations or general framework builds.

## Prepare an operator-owned contract

1. Freeze a clean source revision in a disposable repository. Preserve existing
   instructions; record the source revision and distinguish it from dirty work.
2. Add an OpenSpec change with stable requirement IDs and task IDs.
3. Keep the acceptance policy and selected technology pack outside the worker
   checkout. Inspect and explicitly select the pack; detection grants no authority.
4. Run `cep qualify-toolchains --report /private/path/toolchains.json`. Select only
   the executable bindings required by this task. Paths and receipts stay private.
5. Submit the contract with an explicit active-time budget. No setup application,
   provider activation, integration or deployment follows from acceptance.

```sh
cep run --repo /path/to/disposable/project --spec change-name \
  --policy /private/path/policy.json --budget-minutes 15
```

The policy requires `schema_version: 1` and checks covering `spec`, `tests`,
`security` and `quality`. Each check has a unique ID, operator-resolved absolute
`argv`, mapped `requirements`, timeout, `adapter: "protected-json-cli"` and cases.
Cases must map real assertions to the same gate category and frozen requirements.
Weak operator-authored policies cannot establish meaningful acceptance.

Optional `pack_manifest` selects an external versioned pack; its content digest
joins the frozen contract. Optional `tool_bindings` supplies `{name, executable,
sha256}` rows from qualification. Each executable must be a canonical, bounded,
regular external file, with one link and no group/world write permission. Its
identity is rechecked before worker phases and individual grading invocations.
Only that file receives additional read permission. SDK trees and dependencies
are not automatically granted or fully attested by this executable digest.

`worker_context` is optional bounded operator text for isolation-specific context,
such as deliberately absent parent instructions in a frozen project snapshot.
It cannot grant filesystem, provider, fork or control-plane authority.

## Declare protected cases

Each case has `id`, `kind`, `requirements`, direct `argv` and integer `exit_code`.
Supported optional fields are:

| Field | Meaning |
| --- | --- |
| `fixtures` | Relative filename to UTF-8 text map in a fresh protected fixture root |
| `{fixture}` | Exact argv token substituted with that root; embedded substitutions fail |
| `stdout_json`, `stderr_json` | Expected top-level JSON object subset; nested values match exactly |
| `stdout_empty`, `stderr_empty` | Explicit boolean output-emptiness assertions |
| `forbidden_output` | Literal canaries checked against raw output before redaction |
| `unchanged` | Compare fixture bytes, modes, identities and tree entries; default true |
| `mutable_fixture` | Explicitly place fixtures in disposable writable execution scratch; default false |

Declaration JSON rejects duplicate keys, nonfinite numbers, excessive depth and
oversized input. Cases and fixtures are bounded. Output requires explicit boolean
execution-limit fields; timeout, overflow or truncation fails regardless of exit
code or nominal JSON success. Candidate-owned tests are never imported by the
controller's grader. Exiting before assertions cannot supply required CLI output.
Saved outcomes and broker responses remain redacted; raw security comparison is
available only in trusted controller grading.

Immutable fixtures receive read access separately from each execution's writable
scratch. Mutable fixtures are an explicit testing exception for setup-like CLI
operations and confer no access to original workspace files. The controller checks
cancellation and remaining budget before each invocation, registers its watchdog,
and verifies that the immutable candidate still matches final gates and review.

## Native execution limits

Python and Node in-process execution are verified on the development Mac. uv and
Go version discovery is verified separately; it does not qualify package installs,
compilation or test commands requiring forks. Linux and Windows live execution
remain blocked. Native macOS execution retains filesystem/network/signal denials
and the no-fork lifecycle boundary.

General forks cannot be granted using process-group cleanup alone: detached
children can survive parent exit and cancellation. Apple's [event definitions](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/sys/event.h)
mark the old kqueue descendant-tracking flags unsupported, and its [setsid implementation](https://github.com/apple-oss-distributions/xnu/blob/main/bsd/kern/kern_prot.c)
permits independent process sessions. Polling ancestry is not a verified substitute.
A stronger supported native containment mechanism must pass adversarial lifecycle
probes before fork-dependent toolchains become available. No container fallback
or broad permission change is applied automatically.

## Eventu ownership and scope

The private Eventu adapter uses the ordinary pack loader. It declares relative
commands, technology constraints and capability names, while Eventu-tooling keeps
setup ownership. Private source, provider URLs, account bindings and credentials
stay outside the public platform repository.

The first task rejects invalid persisted bootstrap scopes before planning or
applying configuration. Its external checks include valid/default/recovery behavior,
nonmutation, generic errors, canary leakage and compatibility with minimal legacy
configuration. The original checkout's dirty files are preserved. Any resulting
patch covers the archived source revision only and requires reconciliation and
reverification before integration with later uncommitted work.

A separate fixed-fixture UID experiment now lives outside the runtime. Its source,
failed attempts and remaining qualification contracts are tracked in
[native containment](NATIVE_CONTAINMENT.md). It neither grants forks to jobs nor
qualifies SDK builds. Newer Eventu working changes were reconciled privately with
additional scope-declaration regressions; original integration remains pending the
source branch-policy decision. The older accepted pilot does not cover those changes.
