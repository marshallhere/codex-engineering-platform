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
fork/exec races, orphan cleanup and production UID recovery, inherited Seatbelt restrictions, set-ID
executable exclusion, resource exhaustion and actual uv/Node/Go builds unqualified.
No privileged installation on a developer machine is authorized by these probes.

Darwin returns the effective primary GID in `getgroups()`. Privilege-drop verification
allows only the fixture GID and rejects every foreign group, checks real/effective
UID/GID, and verifies that restoring either UID or GID to root fails. This follows
Apple’s [credential implementation](https://raw.githubusercontent.com/apple-oss-distributions/xnu/main/bsd/kern/kern_prot.c).

The system Python can bind Darwin's account-directory `getgroups` extension, which
fails for anonymous numeric UIDs. Actual credential verification uses the bounded
POSIX `getgroups` symbol from libSystem. Apple's
[extension implementation](https://raw.githubusercontent.com/apple-oss-distributions/Libc/main/sys/getgroups.c)
shows why account lookup is unsuitable. UID allocation also rejects existing GIDs.


`build_probe.py --inspect` describes the separate fixed offline build experiments.
The dedicated `native-toolchain-experiments` workflow verifies pinned SDK archives,
materializes safe internal aliases, freezes root-owned SDK trees and executes fixed
uv/Python, Node and Go recipes after dropping authority. Results establish only
compatibility for those recipes; no experiment changes the shipping no-fork profile.
See [build inputs, receipts and limits](../docs/TOOLCHAIN_EXPERIMENTS.md).

Both privileged experiments reserve each numeric UID durably before forking. A
verified normal cleanup releases that exact reservation only after worker/cleaner
statuses pass and two further inventories are empty. A controller interrupted during
a case leaves a stale record that blocks later allocation. This prevents UID reuse;
it does not terminate or recover an orphan process.
