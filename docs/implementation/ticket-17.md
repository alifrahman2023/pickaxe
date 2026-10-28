# Ticket #17 implementation evidence

Scope: [M1 / T02 — Verify literal bytes, complete fallback, and failure status](https://github.com/alifrahman2023/pickaxe/issues/17),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Execution date: 2026-10-28. This completes the broad input/status slice of
milestone 1; it establishes no acceleration qualification.

## Branch, dependency, and sources

- Continued `ticket/16-git-backed-search` for the owner's explicitly requested
  combined PR #50. The #17 starting commit is
  `3ba7ebd9ec816d7bfcfe0ed3bee13834739070a9`; the combined review baseline remains
  `ab5aaff526cbda6ee55b174ab76ff10f2ff247d6`.
- Native blockers report #16, whose implementation/install/tests and independent
  reviews passed before this slice began. The owner explicitly authorized
  beginning #17 on that implementation in the same PR, with both issues closing
  on merge. The native dependency is preserved; it is not falsely reported as
  closed or bypassed by a failing evidence report. #17 was open/unassigned and
  was claimed for the owner.
- Read the ticket, specification, planning-map Notes, repository guidance and
  glossary, and canonical compatibility, workflow, qualification, build, and
  implementation-plan resolutions. GitHub remains authoritative. Applicable
  sources are linked from the ticket and specification; the CLI-process seam
  was already approved there. Existing untracked local guidance is preserved.

## Changes and explanation

Extended `tests/cli_baseline.py` at the existing CLI-process seam. Production
C++ needed no change: its owned byte strings and direct `execv` argument array
already preserve these inputs and delegate Git's complete search/status.
CTest now writes a lossless raw evidence record for each test method.

- One/two/three-byte needles; space and spaces; tab and tabs; newline and
  newlines; composed/decomposed Unicode; invalid UTF-8; leading hyphens; and
  shell metacharacters are supplied as byte arguments. A controlled external
  executable independently confirms every byte, argument boundary, and terminal
  `--`, without trusting Git's own interpretation.
- Literal byte strings are not decoded text. `std::string` preserves invalid
  UTF-8; NUL terminates a native argument and is therefore tested as blob data,
  not offered as a CLI needle.
- Histories demonstrate count increases/decreases and an edited/moved line
  with unchanged count. Git `-S` excludes the unchanged-count commit while a
  diagnostic `-G` includes it. Line matching is not the product contract.
- A bare clone retains a matching non-HEAD branch, custom format, and explicit
  color. Matching and zero-match fallback searches preserve raw stdout/status;
  stderr contains the single fallback explanation plus any Git diagnostics.
  No index resource is created. A seeded unusable resource remains identical
  in contents, membership, inode, permissions, size, and modification time.
- A real configured text-conversion helper fails only on older blob contents.
  The newest match reaches stdout first; Git then fails. Pickaxe retains the
  same **status 128 and 161 stdout bytes**, never reporting complete success.
  The suite also retains missing/unlaunchable Git, nonrepository, invalid
  operands, and the explicit status-37/partial-output fixture from #16.

The first Unicode fixture incorrectly assumed the decomposed needle must select
the decomposed-content commit on this local Git. Its reference search disproved
that assumption. A separate observation found that `git init` sets
`core.precomposeunicode=true` here; changing that setting changes the reference
outcome. The actual comparison keeps the configuration unchanged. The added
external argument observation confirms Pickaxe itself preserves the original
composed/decomposed bytes. No oracle output or reference configuration was
normalized to obtain a pass.

## Actual checks and retained evidence

- Rebuilt with `cmake --build build` during development; the existing C++20
  Release target still builds. No production type or linking changes occurred.
- Ran individual new checks while extending the fixtures. All six added checks
  pass. The 14-case byte matrix and exact-argument observation each cover every
  listed byte case.
- Two deliberately defective temporary wrappers were rejected: one normalized
  Unicode before invoking Pickaxe; one forced exit zero after a failed search.
  Each corresponding test failed once as expected. These are test-sensitivity
  probes, not production changes or passing product executions.
- Final full implemented suite:
  `ctest --test-dir build --output-on-failure -V` passed **1/1 CTest entries,
  16/16 Python checks**, with no skips. This includes all #16 baseline checks.
- The selected `/usr/bin/git` executable hash and tested `pk` binary hash match
  the identities recorded for #16. OS/compiler/SDK/CMake/Make/runtime identities
  remain the macOS environment recorded in [ticket-16.md](ticket-16.md).
- Raw bundle: [evidence/ticket-17.json.gz](evidence/ticket-17.json.gz). Its JSON
  contains all 16 per-method records, exact argument bytes and stdout/stderr
  encoded as hex, statuses, relevant fixture environment, effective config/ref
  captures, fixture-source and executable hashes, the CTest log, and expected
  negative-control failures. Hex/gzip are storage encodings, not transformations
  used by the comparisons. The gzip round trip was checked against the original
  JSON. Temporary paths identify the actual run; rerun the fixtures to recreate
  repositories. The prior #16 cancellation check uses `Popen`; its detailed
  process trace remains part of #18's pending evidence.

Reproduce the full suite, inspect retained raw records, or run the new
demonstrations using README commands:

```sh
cmake --build build
ctest --test-dir build --output-on-failure -V
gzip -dc docs/implementation/evidence/ticket-17.json.gz > /tmp/pickaxe-ticket-17-evidence.json
```

The saved records are execution evidence, not golden output used by tests.
Each fresh run compares live installed Git with Pickaxe under identical stable
inputs. No acceleration path, index builder, Linux setup, or new product option
was introduced.

## Review and handoff

Applied the code-review skill with independent parallel Standards and Spec
reviewers against `ab5aaff526cbda6ee55b174ab76ff10f2ff247d6...addc30d`.
Commits reviewed: `7f25f58`, `3ba7ebd`, and `addc30d`. Only this review record
changes after review.

### Standards

Pass: **0 documented violations, 0 actionable smell findings**. The combined
diff follows repository guidance/glossary, uses the approved CLI-process seam,
preserves local work, and records the owner-authorized combined-ticket workflow.
No unjustified abstraction or product option was introduced.

### Spec

Pass: **0 findings**. Both tickets' completion checks are satisfied, including
byte arguments, occurrence counts, configured/bare fallback, resource
preservation, and failures after plausible output. The reviewer verified all
16 raw test records, all 14 literal searches, and the matching fixture-source
hash, then independently reran CTest: **16/16 checks passed**.

Standards: 0 findings; Spec: 0 findings; neither axis has an outstanding issue.
`git diff --check` passed and the preserved local files' SHA-256 checks remained
unchanged. The PR covers #16/#17 and includes closing references for both; it
remains unmerged for owner review. The planning map and resolved decisions are
unchanged.

Next ticket at the original #17 handoff:
[#18 — M1 / T03 — Verify cancellation and Git process ownership](https://github.com/alifrahman2023/pickaxe/issues/18),
then open and not started. At that handoff, full process-ownership/terminal cancellation,
candidate/replay feasibility, indexing, memory/publication audits, acceleration
qualification, benchmarks, Linux preparation, and release acceptance remain
pending in their assigned tickets.

Continuation: the owner subsequently authorized #18 in the same PR. Its
completed cancellation/process-ownership checks and current #19 handoff are in
[ticket-18.md](ticket-18.md). The #17 archive remains the historical
16-check/version-2 fixture run; version-3 hashes and the 18-check run are
retained with #18.
