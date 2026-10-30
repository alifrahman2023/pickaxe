# Ticket #24: reference-Git baselines

The owner authorized co-implementation in draft PR #53, using #23's approved
three-needle Git subset. Linux and the original full-role workload remain
deferred. #23's native dependency edge stays intact while both issues remain
open for review; no merge or later ticket is authorized by this work.

## Measurement protocol

`scripts/baselines.py` reads the selected exact-byte metadata, verifies the
original/audited manifest identities and retained streams, and validates the
repository through cached shape/object-file identities without a history walk.
Preflight lists all commands and output paths. There is no cache-miss fallback.
The selected common, rare and zero-match needles are unchanged.

For each query, execute one untimed warm-up followed by five measured warm
runs. Git is the only implementation in the current corpus run. Optional
`--pickaxe` prepares sequential paired comparisons with Git-first/Pickaxe-first
ordering alternating between samples; it keeps the same selected workload.
A pair is never timed concurrently.

The monotonic interval begins before launch bookkeeping/process creation and ends
when foreground command completion is observed. It includes startup, internal
integrity/traversal/helper work, formatting and writes to separate stdout/stderr
files. File opening, metadata collection, counting, hashing and exact byte
comparison occur outside timing. Launch bookkeeping and process creation/wait scheduling overhead are
included and not subtracted. This is captured-output latency, not terminal
rendering or durable-storage latency.

Raw outputs/statuses and every warm duration are retained. Medians and min/max
ranges summarize exactly five successful verified samples; there are no tail,
capacity, speedup or numerical acceptance claims. Warm-ups have no reported
latency. No credible independent cache reset is available, so **cold evidence
is unavailable**. Input pack validation warms caches; new processes are not cold
runs. Interactive desktop background activity limits reproducibility and must
be recorded for each attempt.

The explicit runtime ceiling includes validation, measurement, byte checks and
final checks, with bounded reader cleanup afterward. A failed/mismatching command
or budget expiry preserves partial metadata/raw files, leaves completion absent,
and never retries automatically. A new attempt requires a new output directory.

## Checks and execution

CLI/process tests use disposable tiny Git histories and external executables.
They cover read-only preflight, missing-budget rejection, exact successful
streams, sequential paired ordering, five-sample summaries, nonzero command
status, blocked-reader budget cancellation, and changed saved-output rejection.
No Linux traversal is part of this test loop.

The final shared `python3 scripts/check.py run` passed **42 suite checks and
30 tool/validator tests**, with no skips. Its source-pinned archive is retained at
`evidence/ticket-24-checks.json.gz`. Real Git measurements use 18 commands under
a 30-minute total execution ceiling. No Pickaxe timing or Linux run is scheduled.


Independent Standards and Spec review identified launch-cancellation ownership,
post-publication cancellation, interrupted outcome retention and storage metadata
gaps. All four were fixed and re-reviewed with no residual findings. Interrupted
records retain actual status, duration, raw sizes and incomplete verification.
Atomic final-manifest replacement is the terminal success boundary; subsequent
signals do not revoke completed evidence.


## Completed Git-only measurements

The real run completed all **18 sequential Git commands**: three untimed
warm-ups and fifteen measured warm samples. Every command returned status zero;
every stdout/stderr stream matched the frozen reference, and every saved stream
was rechecked before completion. No retries, Linux searches or Pickaxe timing
were performed. The run stayed within the approved 1,800-second ceiling.

- `common-return`: median **19.806718 s**, range 18.626918–29.593965 s (five warm samples).
- `rare-subscribe`: median **12.888558 s**, range 11.891362–13.256925 s (five warm samples).
- `zero-a`: median **14.574361 s**, range 12.678503–17.523885 s (five warm samples).

The report interval, including initial metadata collection and final checks after
input validation, was 295.009 seconds. It is not a per-query latency sample.
Cold evidence remains unavailable. The host reports Apple M3, eight CPUs and
16 GiB RAM. Workload/output device identities were recorded, but automatic
storage type/SSD details were unavailable and are explicitly limited in the
metadata. These are captured-output warm Git baselines
on an interactive macOS desktop with uncontrolled background activity, not
acceleration qualification, cold-cache results, or universal performance claims.

Raw outputs and partial checkpoints remain locally under
`build/benchmarks/git-baselines-ticket-24/`. The complete metadata, individual
raw durations, statuses, hashes, exact commands, workload/ref/config/packing
identities, OS/Git/Python/CPU/RAM/storage observations and method limitations
are archived in `evidence/ticket-24.json.gz`. This gzip contains metadata rather
than raw stdout/stderr; their paths and hashes are recorded. Its decompressed
bytes were checked against the completed local manifest.

This completes #24 for the owner-approved three-query Git subset. Original
Linux/full-role evidence remains deferred. Both issues remain open for review,
PR #53 stays draft, native dependencies remain intact, and no later ticket is
started.


## Full-PR review fixes

A subsequent full-PR review reproduced surviving helper processes after their
reader exited, a launch/registration cancellation window in standalone
reproduction, and rejection of Pickaxe's valid fallback stderr diagnostics.
Preparation, reproduction and measurements now share protected process ownership
and whole-group cleanup. Pairing checks Pickaxe's stdout/status contract while
retaining its own stderr and checking those bytes for later alteration. Reference
Git reproduction keeps exact stdout/stderr comparison.

Tiny regressions reproduce both lifecycle defects and exercise a paired process
that emits Pickaxe's documented fallback diagnostic. The earlier real Git-only
measurements and their source-pinned archive remain unchanged historical evidence;
no corpus measurements were rerun for these fixes.


The final review-fix revision passed the shared check: **42 suite checks and
32 tool/validator tests**, no skips. Current source-pinned regression evidence
replaces `evidence/ticket-24-checks.json.gz`; the original measurement archive
remains unchanged. Standards and Spec re-review confirmed no residual findings.

An earlier check attempt timed out in the unmodified containment suite. Its
isolated verbose run passed all 16 tests in 7.670 seconds, and a fresh complete
run passed with unchanged CTest limits (17.04 seconds for the three registered
suites). The timeout did not reproduce; no cause is asserted. Failed attempts,
including an earlier fixture-startup failure, remain under `build/checks/evidence/`
and their logs under `build/tickets-23-24/context/`.
