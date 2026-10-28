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
