# Development checks and evidence

Run the same build, full suite and evidence validation used by macOS CI:

```sh
python3 scripts/check.py run
python3 scripts/check.py verify build/checks/evidence/latest.json.gz --current-sources
```

Requires macOS, CMake ≥3.28, Make, Apple Clang with C++20, Python ≥3.8 and Git
on PATH. The existing process/PTY checks need normal local process access.
The command uses its own `build/checks` tree; pass `--build-dir <path>` to change
it. It self-tests evidence validation, configures a Release build, compiles, runs CTest, and retains every attempt
under that build tree's `evidence/run-*` directory. A failed run returns nonzero
and retains its logs. `latest.json.gz` changes only after a successful run.
Command stdout and stderr stream to the console and the attempt's log as bytes
arrive, including output without a newline. Failed commands retain partial logs.

The three registered fixture suites have evidence records for every declared test.
The collector derives expected names from their source, rejects missing/duplicate
records, failed/skipped checks and inconsistent source/Git/binary hashes, checks
execution counts, and verifies the gzip round trip. Validator self-tests must also report a plain
successful completion, no skips, and an execution count matching the source-derived
inventory captured before launch; a zero exit status alone is insufficient. Each new suite with evidence
must be registered in `scripts/check.py`. A new testcase in an existing suite is
discovered automatically. Collection is deliberately fixture-sized and unbounded;
it is not the production indexing memory ledger or qualification tooling.
The publication suite builds a disposable macOS-only C++ probe, records its
binary and C++/Python source hashes, and exercises local APFS behavior. It is
neither linked into nor installed with `pk`. See the [#22 protocol report](implementation/ticket-22.md)
for ordering, failure states and qualification limits. Bundles made before this
suite was registered must be regenerated to meet the expanded suite inventory.

`verify` checks a saved bundle's consistency without comparing to today's source.
Use `--current-sources` when validating a current run. The current collector writes schema 2 with the declared self-test inventory.
Earlier collector schema-1 bundles lack that inventory and must be regenerated
for this stricter validation. Historical ticket #17–#21
archives use their original schemas; this tool does not rewrite or validate them.
Hashes and manifests detect mistakes, not fabricated or malicious evidence.

## macOS CI

`.github/workflows/macos.yml` runs on pushes to `main`, pull requests (including drafts),
and manual dispatch. It invokes the same command and uploads successful evidence
or failure logs. It needs read-only repository permissions and no project secrets.
Official checkout/upload actions are pinned to commit IDs.

The `macos-15` hosted label is selected explicitly instead of `macos-latest`.
GitHub documents its current architecture and resources in the
[hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners).
Hosted images and toolchains change; the bundle records the actual environment
and selected Git. Passing this job is a development regression check, not the
exact macOS 15.7.4 / Git-154 acceleration qualification or Linux release evidence.
Branch protection is separate: configure this job as a required check when ready.

## GitHub operations for agents

Use the repository's authenticated `gh` CLI. Request explicit JSON fields to
avoid legacy default GraphQL selections:

```sh
gh issue view 21 --json number,title,body,state,labels,assignees,comments
gh pr view 51 --json url,state,isDraft,title,headRefOid,baseRefName
```

The installed CLI's default issue/PR reads and `gh pr edit` encountered deprecated
Projects-classic GraphQL fields during this session. Use the REST update below
for a title/body change; it preserves the PR's draft/open state. Keep multiline
bodies in files and encode JSON structurally, without shell interpolation:

```sh
python3 scripts/update-pr.py 51 --title 'PR title' --body-file /path/to/body.md
```

That helper only updates the specified PR title/body. It uses `gh api` against
this repository and prints the resulting URL, state, draft status and head SHA.
It never marks ready, merges, closes issues, assigns tickets or changes labels.
For reads, combine independent requests and retain only needed fields. When a
sandbox denies network access, use the environment's supported escalation for
the network command; repeating the same denied request does not add evidence.
Canonical GitHub decisions remain authoritative; local captures need their source
identities and freshness recorded before reuse.

## Existing approvals

Before asking the owner for a decision, clarification or permission, check:

- The current conversation's approvals, preferences and stopping boundaries.
- The linked specification's approved interfaces and Testing Decisions.
- The ticket's canonical resolution comments and the map's Notes and decisions.
- Applicable repository guidance for the operation.

Apply an existing approval when it covers the proposed action within the current
scope. Ask only about a remaining gap or conflict. If a rule requires the
question, name its source and explain the unresolved point. Approval for a test
seam does not authorize a later ticket or change a merge/closure boundary.

## Benchmark execution cost controls (#23)

The normal check command above uses tiny fixtures. Benchmark `validate` (also
spelled `inspect`) requires `--shape-manifest`: it checks repository inputs and
object-file hashes and reuses the recorded graph metrics. Missing, incomplete or
changed inputs fail; validation never falls back to a history walk. Full walks
use the explicit `characterize` command. `prepare`, `characterize`, `freeze` and
`reproduce` require an owner-approved positive `--budget-seconds` for execution.
This wall-clock limit includes validation and final checks; cancellation has a
short cleanup allowance to terminate and reap owned readers. The flag records a
limit; it does not establish that the owner approved that limit.

Before real-corpus freeze or reproduction, run the same command with
`--preflight` and no budget. This read-only path validates cached inputs and
retained completed streams, then prints every remaining reference command,
needle bytes, output paths, reader count and observed write intervals/bytes.
Write intervals are retrospective diagnostics, not benchmark samples or a
prediction of remaining costs. Fresh `freeze` requires `--shape-manifest`;
`freeze --resume` uses the retained checkpoint's shape instead.

Agree the runtime **and agent-usage** budget before execution. Keep long jobs
out of an active conversational polling loop: retain job logs and inspect once
at the agreed boundary. On exhaustion, owned readers stop, queued readers are
cancelled, completed checkpoints and interrupted raw files remain, and completion
stamps stay absent. Resume archives interrupted streams before retry. The limit
never truncates history or output to satisfy the workload requirements. A small
budget may expire during validation before any reader starts.

The owner subsequently selected three already captured/reproduced Git needles
and deferred Linux. The active subset is recorded in
[the selected evidence](implementation/evidence/ticket-23-selected-git.json);
its saved bytes were reverified without new history searches. No corpus job is
scheduled. The original twelve-role freeze interface remains unchanged.

For a separately approved future resumption of the original Linux protocol,
this is the read-only preflight:

```sh
python3 scripts/benchmarks.py freeze --repo build/benchmarks/linux-volume/linux-B --candidates benchmarks/linux-needles.json --output-dir build/benchmarks/linux-frozen --resume --jobs 2 --preflight
```

Add `--budget-seconds <approved-seconds>` and omit `--preflight` only after the
budget decision. One completed query took about 16 minutes; the deferred original protocol
still has 11 original queries and 12 reproductions pending, with unknown costs.
#24 now uses only the approved three-needle Git subset; PR #53 stays draft. Before changing Git configuration or attribute capture, consult
[the eligibility input inventory](implementation/eligibility-inventory.md).

## Reference-Git baselines (#24)

`python3 scripts/baselines.py` consumes the approved selected evidence, validates
its frozen/audited identities and saved bytes, and reuses the cached repository
shape. `--preflight` lists the complete sequential schedule without searches or
output files. Execution requires the same approved runtime budget as other
expensive tooling. No Linux work is included in the current selection.

```sh
python3 scripts/baselines.py --selection docs/implementation/evidence/ticket-23-selected-git.json --output-dir build/benchmarks/git-baselines --activity-note 'describe relevant current background activity' --preflight
```

For the three selected Git needles the schedule has 18 searches: one untimed
warm-up and five measured warm runs per needle. Replace `--preflight` with
`--budget-seconds <approved-seconds>` to execute into a fresh output directory.
Stdout/stderr go to distinct regular files. The interval covers process startup
through foreground completion; hashes, counts and byte comparisons happen
outside timing. Raw values, statuses, identities, medians and ranges remain in
`manifest.json`, with incomplete attempts retained as `manifest.partial.json`.
A mismatch, cancellation or expiry retains raw streams and leaves completion
absent. No automatic retries or concurrent timed searches are used.

Optional `--pickaxe <executable>` adds one warm-up and five measurements for that
implementation, alternating Git/Pickaxe order by sample and executing each
command sequentially. It doubles the schedule, so review a new preflight and
budget before paired corpus execution. It does not change the selected needles.
Cold evidence is unavailable without a credible independent reset; a new process
is not a cold run. Hashing input packs itself warms caches. Five samples support
median/range reporting, not tail estimates or acceleration qualification.
