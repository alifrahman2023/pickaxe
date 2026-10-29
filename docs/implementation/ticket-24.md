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

Real-corpus measurements and the final check archive are pending the completed
review and fixture check run. The intended real run has 18 Git commands and a
30-minute total execution ceiling. No Pickaxe timing or Linux run is scheduled.


Independent Standards and Spec review identified launch-cancellation ownership,
post-publication cancellation, interrupted outcome retention and storage metadata
gaps. All four were fixed and re-reviewed with no residual findings. Interrupted
records retain actual status, duration, raw sizes and incomplete verification.
Atomic final-manifest replacement is the terminal success boundary; subsequent
signals do not revoke completed evidence.
