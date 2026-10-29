# Ticket #23: frozen benchmark workloads

Work in progress. This report will record measured completion evidence before
#23 closes or #24 begins. Scope: R14 / AC3 of specification #15 and the canonical
benchmark resolution in #5. No acceleration or capacity claim follows from
preparing these source histories.

The branch `ticket/23-24-benchmark-baselines` starts at
`9fa69c3ae626eb6cf4d8e4184e4764483eea0fa2`, the verified PR #52 merge.
Local main was fast-forwarded to origin/main; the old branch and seven untracked
local guidance files were preserved. Only named implementation files are staged.
#22 was already closed when inspected. Its merged publication report and native
#23 blocker edge remain intact; #21 is also closed. #23 was unassigned and was
claimed before implementation. #24 remains blocked by #23.

## Preparation and reproduction

The PATH-selected Git fetches complete ancestors of each pinned B commit into a
bare acquisition repository. There is no depth/filter argument. Preparation runs
`git fsck --full --no-reflogs` over the acquired object database, then creates two
ordinary independent repositories, privately copies the object files, and checks
out pinned A or B on `refs/heads/benchmark`. No alternates, shared writable packs,
remote refs or linked worktrees are used. Existing destination directories cause
failure rather than replacement. Acquisition repositories have no measured role.
No repack is performed; transport pack identities and sizes are retained.

```sh
mkdir -p build/benchmarks/sources
git init --bare build/benchmarks/sources/git.git
git -C build/benchmarks/sources/git.git fetch --no-tags https://github.com/git/git.git 777489f9e09c8d0dd6b12f9d90de6376330577a2
git init --bare build/benchmarks/sources/linux.git
git -C build/benchmarks/sources/linux.git fetch --no-tags https://github.com/torvalds/linux.git adc218676eef25575469234709c2d87185ca223a
python3 scripts/benchmarks.py prepare --root build/benchmarks --name git
python3 scripts/benchmarks.py prepare --root build/benchmarks/linux-volume --name linux
python3 scripts/benchmarks.py freeze --repo build/benchmarks/git-B --candidates benchmarks/git-needles.json --output-dir build/benchmarks/git-frozen
python3 scripts/benchmarks.py freeze --repo build/benchmarks/linux-volume/linux-B --candidates benchmarks/linux-needles.json --output-dir build/benchmarks/linux-frozen
```

Linux requires a case-sensitive checkout filesystem: the pinned tree contains
both `include/uapi/linux/netfilter_ipv4/ipt_ECN.h` and `ipt_ecn.h` (also
`ipt_TTL.h` / `ipt_ttl.h`). The host workspace filesystem fails a distinct-case
file probe. Before preparing Linux, create and mount a disposable image:

```sh
hdiutil create -size 80g -type SPARSEBUNDLE -fs 'Case-sensitive APFS' -volname PickaxeBenchmarks -nospotlight build/benchmarks/linux-workloads.sparsebundle
mkdir -p build/benchmarks/linux-volume
hdiutil attach build/benchmarks/linux-workloads.sparsebundle -mountpoint "$PWD/build/benchmarks/linux-volume" -nobrowse -owners off
ln -s "$PWD/build/benchmarks/sources" build/benchmarks/linux-volume/sources
```

Run this image setup after acquisition starts, before Linux preparation. The
80 GiB virtual limit is sparse, not an up-front physical allocation. Ordinary
non-bare repositories and complete case-distinct files remain available for
later Pickaxe measurements. The image-backed APFS condition must remain explicit
in those measurements; it is not Linux/ext4 qualification. To reuse later,
reattach this image at the same mountpoint. Detach only when no benchmark
process uses it: `hdiutil detach "$PWD/build/benchmarks/linux-volume"`.

Use a new build directory for a new preparation/freeze attempt. The source
histories are Git and Linux **source workloads on macOS**; no Linux operating
system is prepared. The frozen inputs apply to future measurements, including
slowdowns/failures/fallback, without changing the needle manifests.

A checkout alone does not freeze `--all`: another branch or worktree can add
eligible history. `inspect` refuses extra refs, a detached/mismatched HEAD,
linked worktrees, a dirty checkout, shallow history, partial-clone configuration
and object alternates. Both A/B manifests record exactly one benchmark branch.
A private copy of B's objects contains objects outside A's scope; those objects
are counted explicitly and never treated as searched history.

## Definitions and selection

- Reachable commits and parent-edge/merge/root counts come from
  `git rev-list --all --parents`. A merge has more than one parent; maximum
  parent count and total parent edges describe the merged graph, not just a
  first-parent chain. The one live branch does not imply linear history.
- Unique reachable objects come from `git rev-list --objects --all`; each unique
  reachable blob's uncompressed `cat-file` size is counted once. Repeated paths,
  content reuse and pack deltas do not multiply this volume. The ten largest
  blobs retain object IDs and byte lengths.
- Packed object bytes are the sum of `.pack` file lengths, excluding indexes,
  checkout, loose objects and acquisition copies. `count-objects -v`, each pack's
  length/hash, reachable type counts and logical object bytes are retained.
  Out-of-scope objects are all unique stored objects minus unique reachable
  objects; they are distinct from live refs and search scope.
- `common`/`rare` describe relative reference-match counts within this suite,
  without a universal cutoff. Every rare needle must match, and each common
  count must exceed both rare counts. Roles can overlap semantically.
- Zero-match means no commits selected by the reference search. No claim of
  absence in every historical blob is made.

Candidate selection uses source vocabulary, README passages and fixed arbitrary
zero-match markers, without any Pickaxe timing. Common candidates are familiar
source terms; rare candidates are specific README phrases. Short bytes are `x`
and `qr`; Unicode is UTF-8 `René`; long/newline candidates are exact README
passages. `benchmarks/*-needles.json` preserves argument bytes in hexadecimal;
no shell evaluation, normalization, regex conversion or embedded NUL is used.
Common/rare classification uses selected commits, never current-checkout
occurrence counts. Any unsuitable candidate attempt remains in local build
storage and replacements will be recorded below.

The benchmark environment deliberately excludes inherited `GIT_*` variables,
system/global Git config, and sets C locale/UTC. Private workload config records
fixed non-relative dates, medium formatting, no color/decorations and disabled
auto-GC. This is a declared reproducible benchmark profile, not a change to
product configuration semantics or acceleration eligibility. The exact reference
invocation remains `git --no-pager log --all <single -Sneedle argument> --`.
Successful default-format `commit <40-hex>` headers count selected commits;
messages are indented by medium formatting. Captured streams/statuses, output
sizes and hashes are retained, with a second complete search per needle proving
reproduction. No timing data determines the frozen inputs.

## Checks and pending evidence

The implement and TDD skills were applied at the approved CLI process/local-Git
seam. Before implementation, the history-shape test failed because the tool did
not exist. A second red check showed the absent `freeze` command. Tiny histories
exercise independently known historical blob volume, rejection of extra refs,
empty/NUL rejection, match counts and exact newline arguments/output.

The first sandboxed full check failed at existing local-socket cancellation
fixtures (`EPERM`). With normal process access, all 42 suite checks passed; the
collector correctly rejected source changes during the run. Both failed
attempts remain under `build/checks/evidence/`. Final sealed checks, all four
shape records, frozen needle outputs and reviews are still pending.


## Preliminary review and filesystem finding

Independent code-review Standards and Spec reviews examined the change from the
recorded starting commit. Standards found no documented-standard breach and one
P2 correctness issue: an accepted ID ending in `-reproduced` could overwrite a
retained original capture. A red→green regression now reserves that suffix.
Both stream files also receive explicit byte comparison, beyond length/hash
checks. The follow-up Standards review confirmed the fix and all four workload
CLI tests passed; no new finding. Preliminary Spec review found zero findings,
with actual large-workload completion still pending. Final review includes the
completed evidence and any #24 change.

The current in-flight Git capture started with the original tool source (commit
`18dc85d93bbfc7cc5c6428c7d1154de8ad310335`); its source hash remains in its
manifest. Its selected IDs cannot collide. After reproduction completes, every
original/reproduced stream will also be compared byte-for-byte, and that result
will be recorded separately. Linux captures use the corrected source.


A targeted Spec follow-up found a second reproducibility gap: Git's default
user/system attribute files are separate from global/system gitconfig. The tool
now records applicable external user, system and repository `info/attributes`
paths with absent/present/disabled state and hashes, plus HOME/XDG values.
Git expands `%(prefix)/etc/gitattributes` itself to identify its system path;
no path is inferred from the macOS `/usr/bin/git` shim. A red CLI observation
lacked this metadata; the corrected check detects creation of an info attribute
file even though tracked checkout bytes remain unchanged. Initial/final audits
protect corrected captures. The Spec reviewer confirmed this fix, and the
suggested declared-environment and disabled-attribute handling are included.

An additional fixture caught a JSON round-trip mismatch: in-memory largest-blob
pairs were tuples while decoded manifest pairs were lists. The returned shape
now uses JSON-stable lists. The reproduction CLI test passes and deliberately
changed retained stdout fails without a completed verification record. Git's
first audited attempt failed before launching queries due to that mismatch;
its original successful freeze remains intact.

The first Linux GitHub transfer failed with `curl 56` / connection reset / early
EOF after approximately 2.1 GiB. Its incomplete temporary pack and failure record
are retained in `build/benchmarks/failed-linux-acquisition/`, outside valid
object storage; no incomplete object database is used as a workload. Acquisition
is retrying from `https://kernel.googlesource.com/pub/scm/linux/kernel/git/torvalds/linux`
with transient `http.version=HTTP/1.1`, the same pinned commit, no depth/filter,
and actual source/transport recorded in `acquisition.json`. Preparation still
requires a successful full fsck and closed ancestor traversal before use.

For Git's original captures, `reproduce` re-executes every frozen query under
initial/final dependency audits and directly compares both streams to retained
original bytes. The resulting `verified.json` records its interval and current
source/environment identities. It explicitly does not infer historical absence
of attribute files from their later observed absence.

```sh
python3 scripts/benchmarks.py reproduce --repo build/benchmarks/git-B --frozen build/benchmarks/git-frozen --output-dir build/benchmarks/git-audited-reproduction
```
