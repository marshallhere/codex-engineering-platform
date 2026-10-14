# Independent security finding dispositions

The restricted live probes and the deterministic gate checks are separate from
static analysis. Bandit 1.8.6 was executed under Python 3.13 because its Python 3.14
AST support failed. The report contains 15 LOW findings, zero MEDIUM/HIGH and no
scanner errors. The independent audit reviewed all call sites on 2026-10-14.

| Finding | Disposition |
| --- | --- |
| B404 subprocess imports | Required for trusted controller, Git, watchdog and exception handling |
| B603 CLI background launch | Absolute isolated Python, fixed bootstrap, separate argv, no shell |
| B603 demo bootstrap | Fixed disposable Git operations; disabled hooks and global/system configuration |
| B603 evidence Git calls | Sanitized environment; filters/includes rejected; hooks/fsmonitor disabled |
| B607/B603 snapshot init | Fixed Git command with system-only PATH and empty templates |
| B603 watchdog | Trusted isolated bootstrap, validated protected registry and UUID |
| B606 lifecycle execvpe | Direct argv released only after durable watchdog registration |
| B603 generic process helper | Bounded direct argv; worker callers require the separate native wrapper |

The reviewed baseline retains findings; no `nosec` directives or scanner exclusions
were added. `scripts/security_gate.py` rejects scanner errors, any higher severity,
and new LOW finding counts outside the reviewed set. Review actual call sites after
changes: a count baseline cannot prove a changed call remains safe.

These dispositions assume protected runtime code and trusted operator executable
resolution. The generic process helper is not itself a sandbox. New callers must
not pass worker-selected commands directly to it. Platform acceptance still requires
native qualification, protected gates and a fresh independent read-only Codex review.
