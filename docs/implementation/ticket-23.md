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
python3 scripts/benchmarks.py prepare --root build/benchmarks --name linux
python3 scripts/benchmarks.py freeze --repo build/benchmarks/git-B --candidates benchmarks/git-needles.json --output-dir build/benchmarks/git-frozen
python3 scripts/benchmarks.py freeze --repo build/benchmarks/linux-B --candidates benchmarks/linux-needles.json --output-dir build/benchmarks/linux-frozen
```

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
