# Ticket #23: frozen benchmark workloads

Work in progress for #23 only. This report will record measured completion
evidence before #23 closes. The owner stopped scope at #23; #24 remains unstarted. Scope: R14 / AC3 of specification #15 and the canonical
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

The commands below record the original preparation. Current execution requires
the [cost preflight and approved budget](../development.md#benchmark-execution-cost-controls-23);
reuse the retained histories rather than repeating acquisition or preparation.

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
python3 scripts/benchmarks.py freeze --repo build/benchmarks/git-B --shape-manifest build/benchmarks/git-B.json --candidates benchmarks/git-needles.json --output-dir build/benchmarks/git-frozen
python3 scripts/benchmarks.py freeze --repo build/benchmarks/linux-volume/linux-B --shape-manifest build/benchmarks/linux-volume/linux-B.json --candidates benchmarks/linux-needles.json --output-dir build/benchmarks/linux-frozen
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


The completed Git audited reproduction compared **24 streams** (stdout and
stderr for twelve queries) byte-for-byte, with unchanged dependency identities
from 2026-10-29 17:03:05 UTC through 17:07:26 UTC. Git A's original shape also
reproduced against the corrected inspector. The corrected-source shared Release
build passed **42 suite checks and 21 tool/validator tests**, no skips; the sealed
bundle is `docs/implementation/evidence/ticket-23-checks.json.gz` and verifies
with current sources. Earlier denied/changed-source/timeout attempts remain
retained rather than counted as passes. Linux completion remains pending.


## Validation latency correction

The original tool repeated full `rev-list` / `cat-file` characterization at
freeze entry/exit and reproduction, despite already completed frozen A/B
reports. After owner feedback, the redundant Linux scans were stopped; the
successful full fsck, source acquisition and all four initial full shape reports
were preserved. No workload, needle role or measurement repetition was reduced.

Full characterization remains an explicit one-time operation per prepared
snapshot. `inspect --shape-manifest <prior report>` and `freeze --shape-manifest
<prior report>` instead validate pinned refs/HEAD, clean checkout, config,
external attributes and SHA-256 hashes of every object-storage file (packs,
indexes and auxiliary metadata). They reuse the prior graph/blob metrics and
record that method plus the source report path and SHA-256. They do not claim
independent recomputation. Reference queries and their byte reproduction still
execute in full; the subsequent warm-run measurements remain separate.

New cache state schema 1 requires every repository dependency and graph metric
field. Missing fields and changed indexes are rejected. For the session's older
fully packed reports only, matching pack bytes and object counts plus exactly
the expected pack/index files permit promotion; newly hashed indexes establish
current identity, not their historical identity. Legacy omissions are explicitly
limited to the fields absent from those older reports. Grafts, shallow history,
alternates and symlinked object storage are rejected.

A local Git wrapper blocks every `rev-list` / `cat-file` invocation. The original
repeated-inspection path fails this guard immediately. The new validation path
passed it on the real Linux B workload in 4.963 seconds initially and 8.783
seconds with the reviewed schema/provenance checks during a full check run, hashing its retained
object files without walking history. The regression also demonstrates that
changed object storage and incomplete reports cannot reuse stale metrics.
Independent Standards review confirmed the fixes with no outstanding finding;
Spec review accepted identity-checked reuse and required explicit provenance,
which is now recorded. Raw diagnostic records are under
`build/benchmarks/diagnosis/`. The tiny wrapper is diagnostic-only.

Downloading and characterizing the fixed histories is not part of ordinary
builds or tests. The actual full-history reference searches are deliberately
repeated by the approved benchmark protocol and can remain expensive. Changes
to the recorded workload/packing invalidate reuse; validation fails rather than
silently declaring a different dataset equivalent.


After the latency correction, the full shared Release checks passed again:
**42 suite checks and 21 tool/validator tests**, no skips. The source-pinned
archive was refreshed to that successful run; earlier versions remain in Git
history and local attempt directories. The large datasets are absent from the
ordinary test loop: five tiny workload-tool tests exercise the relevant CLI
behavior without downloads or Linux history enumeration.


## Untimed parallel capture and retained checkpoints

The first Linux primary query (`return`) completed successfully with 332,656
matches and 290,880,503 stdout bytes. Its exact original stream and checkpoint
are retained. Before the next query completed, the sequential process was
stopped at that checkpoint to enable two independent Git readers for the
remaining **untimed preparation**, not performance measurement. No #24 tooling
or measurements have been started, following the owner's narrowed scope.

`freeze --jobs 2` bounds concurrent preparation readers; each query writes its
own raw files. Captures are placed in the manifest's declared needle order,
regardless of completion order. The reproduction phase still runs complete
reference searches and compares stdout/stderr bytes. These concurrent runs
must not be reported as foreground latency measurements.

`freeze --resume` validates repository/object identity, selected Git executable,
build/config/environment, exact candidate bytes and every retained successful
capture before reusing it. It preserves the prior checkpoint, its hash/source
identity and reused query IDs. Unfinished output files move to a separate
`resume-*` directory before retry, retaining interrupted data. Completed
reproduction records are reused only after their raw files compare to originals.
The tool rechecks every retained stream and all repository inputs before a
completed manifest is written. Checkpoint replacement is atomic for visibility;
no power-loss durability guarantee is claimed for this development evidence.

```sh
python3 scripts/benchmarks.py freeze --repo build/benchmarks/linux-volume/linux-B --candidates benchmarks/linux-needles.json --output-dir build/benchmarks/linux-frozen --resume --jobs 2
```

Tiny CLI fixtures require two queries to overlap, prohibit rerunning a completed
query on resume, preserve an interrupted stream and check exact counts/newline
bytes. Active readers are owned and terminated on capture-batch failure, and
queued captures are cancelled. No experimental acceleration or product index
resource is introduced.


Independent review of parallel/resumed preparation found two P2 edge cases.
A resumed, rejected zero-match candidate could bypass its role check; role
validation now applies to retained, new and final records. Parent-only SIGTERM
could bypass reader cleanup; it now raises through cancellation, including
capture submission. Red→green CLI checks reproduced both failures and now
verify rejection/no completed manifest and termination of two blocked readers.
All five workload tooling tests passed. The actual retained `return` capture is
successful and unaffected by either fixture-only failure scenario.


Both review findings were confirmed fixed with no outstanding Standards or Spec
finding. The final orchestration revision passed the full shared Release build:
**42 suite checks and 22 tool/validator tests**, no skips. Its source-pinned
archive supersedes the earlier checkpoint archive at the same path; historical
versions remain in Git and local attempt directories. #24 remains unstarted.


## Execution controls and pending budget

The follow-up control slice separates cached `validate`/`inspect` from explicit
`characterize`. Validation refuses missing or changed dependencies without a
history walk. Fresh freeze uses a shape manifest; resumed freeze verifies the
checkpoint shape. Expensive execution requires positive, finite
`--budget-seconds`. Freeze/reproduction preflight lists the actual remaining
commands, exact needle bytes, output policy and observed capture sizes/write
intervals without launching readers or modifying retained evidence.

Budget exhaustion cancels queued captures, terminates owned reader process
groups (with a forced-stop fallback), and stops worker-side output scanning and
hashing cooperatively. Successful checkpoints and interrupted files remain;
completion stays pending. The check runner pins sources before self-tests and
rejects source additions, removals or body changes before configuration and at
completion. A disposable subprocess regression changes a source body while the
test inventory remains fixed.

The mounted retained Linux B preflight reported **23 commands: 11 originals and
12 reproductions**, with two readers requested. Its one completed original is
`common-return`: 290,880,503 stdout bytes and approximately 954.254 seconds from
file creation to last write. This is an observed diagnostic interval, not a
latency sample or a forecast. The generated plan is retained locally at
`build/tickets-23-24/context/linux-preflight.json`. Preflight ran without any
history searches; the partial corpus checkpoint and raw streams were preserved.

Independent Standards and Spec review found preflight counting/retained-stream
validation gaps and cancellation during worker hashing; all were corrected and
re-reviewed with no residual findings. Tiny fixtures cover new/resumed preflight,
missing-budget refusal, exact reproduction plans and altered-stream refusal,
budget expiry with two readers ignoring SIGTERM, and the source-body regression.

No numeric runtime or agent-usage budget has been approved. The full-corpus job
remains stopped, #23 incomplete, #24 unstarted, and PR #53 draft. The existing
`ticket-23.json.gz` workload archive still has `complete=false`.

The final control revision passed `python3 scripts/check.py run`: **42 suite
checks and 25 tool/validator tests**, no skips. Updated source-pinned evidence is
retained at `docs/implementation/evidence/ticket-23-checks.json.gz`; this is
fixture evidence only and does not complete the workload archive. The seven
original local guidance hashes still match the handoff capture, and the
untracked retrospective is preserved.
