# Ticket #22 macOS publication investigation

**Result: the narrow local APFS experiment passed.** The proposed ordering is
credible for continued implementation; no fundamental publication-contract
failure was observed. This is early risk evidence, not a qualified durable
product index, an acceleration profile, or a power-loss experiment.

Scope: [#22 — Investigate the macOS publication protocol](https://github.com/alifrahman2023/pickaxe/issues/22),
requirements R05/R10/R12 and cross-cutting invariants in
[specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Executed 2026-10-28. `pk` still performs complete Git fallback.

## Starting state and canonical inputs

- Fresh branch `ticket/22-macos-publication`, starting commit
  `efd3ca7c08152886073b7b612519b754a92191f9`. Fetched `origin/main`, switched to
  local `main`, fast-forwarded without rewriting history, then created this branch.
  Preserved the former ticket branch and all seven original untracked local
  files byte for byte. Only named ticket files are staged.
- Verified [PR #51](https://github.com/alifrahman2023/pickaxe/pull/51) is merged at
  that commit with successful macOS CI. Read the merged #19–#21 reports, evidence
  and review results; reran the shared checks on the merge: **34 suite checks
  and 13 validator tests passed**. Closed those completed tickets as authorized,
  retaining native dependency edges. #22's #20 edge remains; its open-blocker
  count is now zero. #22 was claimed and stays open.
- Read AGENTS.md, tracker/triage/domain guidance, GLOSSARY.md (no applicable
  ADR exists), [map #1 Notes](https://github.com/alifrahman2023/pickaxe/issues/1),
  and the canonical [architecture](https://github.com/alifrahman2023/pickaxe/issues/6#issuecomment-6428299180),
  [qualification](https://github.com/alifrahman2023/pickaxe/issues/8#issuecomment-6454602425),
  [build](https://github.com/alifrahman2023/pickaxe/issues/14#issuecomment-6455044184)
  and [plan](https://github.com/alifrahman2023/pickaxe/issues/7#issuecomment-6456274654)
  resolutions, refreshed from GitHub this session. Canonical capture hashes and
  capture time are retained with the experiment evidence.
- Applied implement and TDD at the specification's approved development-only
  filesystem/synchronization control seam. Observable checks run the experiment
  as a separate process and inspect bytes, status, file identities and artifacts.
  The protocol trace records ordering; it does not independently prove persistence.

## Complete proposed ordering and API review

`tests/helpers/publication_probe.cpp` is a test-only C++20 process. Its payload
is a fixed 15-byte fixture, not an index format. The resource is an already
created, disposable, private directory. Cooperating processes alone modify it.
No repository index, resource discovery, recovery implementation or product
indexing command is introduced.

```text
open stable writer.lock with O_CLOEXEC; flock(LOCK_EX | LOCK_NB)
refuse unexplained recovery; create unique replacement in the resource
write all bytes; read back and validate fixture contents
fsync(replacement); fcntl(replacement, F_FULLFSYNC)
if current exists: link(current, recovery), refusing any existing recovery
fsync(directory); fcntl(directory, F_FULLFSYNC)
rename(replacement, current)                  # atomic visibility boundary
fsync(directory); fcntl(directory, F_FULLFSYNC)
API-level commit confirmation                # qualified protocol must justify durability
unlink(recovery), if present
fsync(directory); fcntl(directory, F_FULLFSYNC)
release descriptors/lock
```

The writer lock covers construction, publication and cleanup. It is never
unlinked or replaced. It is advisory: a program ignoring the lock can still
damage files. `O_CLOEXEC` avoids retaining writer ownership in an executed Git
helper. A fork temporarily duplicates references; explicitly unlocking in the
child would also affect the parent's shared lock. The experiment instead closes
the inherited descriptor through exec. [Apple flock manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/flock.2.html)
and the selected SDK's `flock.2` describe these semantics.

Hardlinks add names for the same file data on one filesystem. The recovery link
therefore preserves the previous file without copying its contents. Rename
atomically changes the name used by new opens; readers already holding a
descriptor retain the old file. Removing its last name does not reclaim storage
until those readers close. Several overlapping readers can consequently retain
several generations. This ticket exercises one replacement, not that later
multi-generation qualification. See Apple's [link](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/link.2.html),
[rename](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/rename.2.html)
and [unlink](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/unlink.2.html)
manuals.

Atomic visibility and durable installation are separate obligations. Apple's
[fsync manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fsync.2.html)
warns that drive caches can reorder or lose data despite `fsync` success. Its
[fcntl manual](https://developer.apple.com/library/archive/documentation/System/Conceptual/ManPages_iPhoneOS/man2/fcntl.2.html)
describes the stronger flush request. The current local SDK 15.5 `fcntl.2`
explicitly includes APFS and describes persistence of earlier same-device
`fsync` operations after successful `F_FULLFSYNC`; that newer detail is absent
from the old web archive's filesystem list. The evidence retains the actual
SDK manual texts, paths and SHA-256 hashes, rather than attributing that detail
to the old page.

The experiment conservatively calls both APIs on the directory before and
after rename, and after cleanup. It does not substitute ordinary `fsync` if
`F_FULLFSYNC` fails. `F_BARRIERFSYNC` is not used: the SDK distinguishes ordering
from persistence on return. Both directory operations returned success on the
observed APFS mount. This supports the candidate protocol; successful calls
alone do not prove APFS recovery behavior or honest hardware cache flushing.
The production qualification must review those assumptions and targeted faults
together before treating this as confirmed durability.

## Observed states and errors

| Boundary | Experiment result | Artifacts and meaning |
| --- | --- | --- |
| Before rename | Nonzero; prior data preserved | Injected `EIO` at recovery-directory full sync leaves old current, its recovery hardlink and new replacement. No rename or cleanup follows. |
| Rename succeeded, final sync failed | Nonzero; publication uncertain | Closing the directory descriptor just before `F_FULLFSYNC` causes actual `EBADF`. New current is visible; old backup remains. No rollback or old-current promise. |
| Final directory flush succeeded | Commit confirmation | Only now may the candidate protocol report installation, subject to its qualification assumptions. |
| Cleanup after commitment failed | Success with installed/cleanup-incomplete warning | Injected unlink `EIO` retains the backup. Installation is not reclassified as failed. |
| Unexplained recovery exists | Nonzero, actual `EEXIST` classification | Prior bytes/inodes and the unexplained file remain untouched; no replacement is created. |

All publication operations check return values. Short positive writes are
completed; zero progress is an error. No retry after an operation error, weaker
flush fallback, rollback, deletion of recovery evidence or automatic promotion
of scratch occurs. Actual and injected failures are distinguished in the trace.
The descriptor RAII owner closes descriptors during unwinding without deleting
named artifacts. Full cancellation/signal behavior, close-error policy and
cause-specific product recovery guidance remain later work.

## Eight narrow checks and actual environment

The suite exercises first installation; complete replacement ordering with a
checkpoint after synchronized hardlink creation; an old open reader through
replacement/unlink; second-writer rejection and stable lock inode; kernel lock
release after SIGKILL; no lock retained by a live PATH-selected Git helper;
the three failure states above; and refusal of an unexplained recovery file.
At the checkpoint, current/recovery have equal device/inode and link count two.
After cleanup, the old descriptor has link count zero and still reads old bytes;
a fresh open reads the new inode/bytes. A writer is rejected during the checkpoint.
Five-second subprocess limits detect blocking; no latency benchmark is claimed.

The Git check uses `hash-object --stdin` in a disposable repository. An exec
handshake confirms launch, stdin keeps Git alive, then the parent closes its own
lock descriptor. A separate writer can acquire the lock while Git still runs.
A temporary mutant removing only the lock's `O_CLOEXEC` fails this check with
busy status 3, establishing that the check detects the intended inheritance bug.

Actual host: macOS **15.7.4 / 24G517**, arm64, Darwin 24.6.0; Apple Git
**2.39.5 / Git-154** at `/usr/bin/git`; Apple Clang **17.0.0 /
clang-1700.0.13.5**, bundled libc++ and SDK **15.5**; CMake **4.1.2**, Make **3.81**.
`statfs` observes local APFS, `/dev/disk3s5` mounted at `/System/Volumes/Data`,
flags **76583040**. `mount` reports `apfs, local, journaled, nobrowse, protect,
root data`; `diskutil` reports internal solid-state storage over Apple Fabric,
FileVault enabled. Disposable resources and the checkout use that Data volume.
`F_FULLFSYNC` is SDK constant **51**, obtained by compiling the header, not
guessing it in Python. Command outputs and relevant storage identities are retained.

Assumptions: an existing private local resource, directory/file permissions,
cooperating writers, immutable published files, same-filesystem hardlinks and
rename, working synchronization APIs and hardware honoring flush requests.
Resource creation's parent-directory durability is not exercised here. Network,
FUSE, overlay and host-shared filesystems are outside this evidence. There was
no Linux preparation, qualification or operating-system substitution.

## Runnable demonstrations and checks

```sh
python3 scripts/check.py run
python3 scripts/check.py verify build/checks/evidence/latest.json.gz --current-sources
python3 tests/publication_protocol.py --probe build/checks/publication_probe -v
```

The reader test shows why a pathname differs from an open file description;
the latter survives renaming and unlinking. In C++, the noncopyable `Descriptor`
owns one descriptor and closes it on scope exit. Its lifetime preserves access
to the file; it does not synchronize directory names or flush storage.

For visible operation traces in disposable resources only:

```sh
demo=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-publication-demo.XXXXXX")
mkdir "$demo/ok" "$demo/uncertain"
printf 'old generation\n' > "$demo/ok/current"
printf 'old generation\n' > "$demo/uncertain/current"
./build/checks/publication_probe inspect "$demo"
./build/checks/publication_probe publish "$demo/ok"
./build/checks/publication_probe publish "$demo/uncertain" close-before-directory-after-fullfsync
# Expected nonzero status on the last command. Inspect both names, without rollback:
cat "$demo/uncertain/current" "$demo/uncertain/recovery"
ls -li "$demo/ok" "$demo/uncertain"
```

Observed output: normal installation reaches `commit confirmed` / `state installed`;
the controlled real API error reports errno 9, `state publication-uncertain`,
new current bytes and old recovery bytes. These seeded fixture files are not
previously qualified durable generations. The Python harness cleans its own
temporary directories after recording observations; the demo leaves its named
temporary directory for inspection.

Full implemented checks: **3/3 CTest entries, 42/42 suite checks and 16/16
validator tests passed, no skips**. C++20 Release build passed with the configured
warnings. The shared collector now includes the probe binary and C++/Python
source identities; three added validator checks reject absent/changed C++ hashes
and a mismatched probe binary. All previous CLI/containment/replay/dependency
checks reran under the canonical full-rerun policy.

[evidence/ticket-22.json.gz](evidence/ticket-22.json.gz) retains the shared bundle,
raw subprocess streams/status, protocol traces, device/inode/link/byte observations,
source/Git/probe/product hashes, baseline result, red tests, mutation result,
environment/API documentation identities and source-capture provenance. Validate it:

```sh
python3 scripts/check.py verify docs/implementation/evidence/ticket-22.json.gz --current-sources
```

Collection preceded the implementation commit: the bundle records the starting
revision and dirty working-tree status, with source hashes identifying the tested
contents. Current-source verification binds those contents to this committed
implementation. Only review/handoff documentation changed after that full run.

## Remaining qualification and handoff

#31–#33 own canonical resource/alias coordination, real format validation,
complete publication faults and interrupted attempts, several reader-held
generations, disk/short-write/link/rename/sync failures, cancellation on both
sides of commitment, live-owner/ambiguous manual recovery and detected input
changes. #38 owns closing the macOS lifecycle evidence for qualification. Review
directory synchronization and flush behavior on the frozen actual environment,
including resource-parent creation, supported storage/mount constraints and
recovery assumptions; revisit the protocol if those cannot credibly be met.
SIGKILL here tests lock release only. Process termination is not a power-loss
simulation, and no arbitrary hardware-failure survival is promised.

The next ticket is **#23, not started**; it remains blocked by open #22. This
branch implements only #22 and stops at a new draft PR, before marking ready,
merging, closing #22 or starting another ticket.

## Review

Applied the code-review skill with independent parallel Standards and Spec
reviewers against `efd3ca7c08152886073b7b612519b754a92191f9...9d44a80`.

### Standards

Pass: **0 documented violations, 0 actionable smell findings**. The reviewer
confirmed guidance/glossary/build conventions, test-only scope, source-pinned
evidence and the distinction between observed behavior and qualification.
Independently reran **8/8 publication checks**, verified the **42-check** archive
against current sources and passed `git diff --check`. No concrete correctness
defect was found within the experiment scope.

### Spec

Pass: **0 findings**. The reviewer confirmed the required lock/helper,
hardlink/reader, synchronization/order, failure-state and environment/limit
coverage; later lifecycle/full faults and Linux work remain deferred.
Independently reran **8/8 publication checks**, verified **42 suite records** and
the **16 validator-test inventory**, the inheritance mutant failure, and all
**seven original local-file hashes**. No missing/partial requirement, scope
creep or incorrect implementation was found within #22's investigation scope.

Final axis totals: Standards 0 findings; Spec 0 findings. Only review/handoff
documentation changed after review. The archive's current-source verification,
whitespace check and original local-file hash verification passed afterward.
The new PR remains draft; #22 and its blocking edge to #23 stay open/intact.
