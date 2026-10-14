# Persist disposable numeric UID reservations across controller interruption

The fixed UID and toolchain experiments currently hold only an invocation-local flock. A killed root orchestrator can release that lock before its worker drops or before cleanup starts; a later invocation cannot infer the fixture UID from process inventory while the worker is still root. This change records each reserved UID durably before worker creation, excludes every unresolved reservation from allocation, and removes one only after successful worker/cleaner completion and repeated empty UID inventory. Stale or ambiguous records remain quarantined. It does not add automatic recovery or a production runtime backend.

## Scope
- Add a private root-owned bounded reservation journal shared by both disposable experiments.
- Bind records to random reservation IDs and numeric fixture UIDs; reject unsafe files, malformed data and duplicate active reservations.
- Reserve before `fork`; release only after explicit successful statuses and repeated empty inventory.
- Add interruption controls that kill an orchestrator after fork and verify a second allocation cannot reuse its UID.

## Out of scope
- Automatically killing or recovering an orphan worker.
- Proving root worker death, full OS/runner power-loss recovery, arbitrary workloads, network/filesystem confinement or UID reuse across hosts.
- Changing the installable runtime or enabling forks.
