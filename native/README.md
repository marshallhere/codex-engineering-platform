# Experimental native UID probes

This directory is deliberately outside the installable runtime. The shipping
runner still denies forks. No experiment can produce an accepted CEP job.

`python3.14 native/uid_probe.py --inspect` performs read-only prerequisite checks.
`--qualify` is restricted to the dedicated `native-uid-experiments` workflow on a
GitHub-hosted disposable macOS runner. The workflow runs on this experimental branch’s relevant pushes or a manual dispatch.
It does not install a helper, create a
Directory Services user, or change this Mac's permissions.

The prototype measures UID membership after session changes, closed pipes and
bounded concurrent forks. A separately forked cleanup process permanently drops
to the fixture UID before signalling. Kernel signal authorization therefore limits
cleanup even if a PID is reused by another UID. See Apple's
[signal implementation](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/kern_sig.c)
and [process information ABI](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/sys/proc_info.h).

An environment marker is an accidental-use guard, not a security sandbox. Run only
reviewed code in disposable CI. Inventory snapshots do not atomically prevent forks.
Even passing probes leave durable root-owned leases/watchdogs, launch revocation,
fork/exec races, UID quarantine/reuse, inherited Seatbelt restrictions, set-ID
executable exclusion, resource exhaustion and actual uv/Node/Go builds unqualified.
No privileged installation on a developer machine is authorized by these probes.

Darwin returns the effective primary GID in `getgroups()`. Privilege-drop verification
allows only the fixture GID and rejects every foreign group, checks real/effective
UID/GID, and verifies that restoring either UID or GID to root fails. This follows
Apple’s [credential implementation](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/kern_prot.c).
