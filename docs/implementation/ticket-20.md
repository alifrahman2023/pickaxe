# Ticket #20 ordered replay feasibility gate

**Gate: PASS for the tested tiny, default-output fixture cases on the current
macOS Git.** This is early feasibility evidence, not acceleration qualification,
a production replay path, or a speedup claim.

Scope: [#20 — M2 / T05 — Pass the ordered Git replay feasibility gate](https://github.com/alifrahman2023/pickaxe/issues/20),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Execution date: 2026-10-28. Product `pk` remains complete Git fallback.

## Starting state and sources

- Continued branch `ticket/19-candidate-containment`, draft PR #51, on the owner's
  instruction to implement the next ticket. #20 starts at
  `8296457bafa48f065d98a58387bff734304c201e`. The combined PR starts at
  `b76a046b383afb3b7fc7652813fdc87e1d9268ec` (merged milestone-1 PR #50).
- Native #19 blocker remains open. Its passing implementation, raw evidence and
  independent reviews were complete before the owner authorized this
  continuation atop it. No blocker was closed or dependency removed; a failing
  evidence report has not been counted as satisfying a gate. #20 was
  open/unassigned and was claimed for the owner.
- Read #20, #15, map #1 Notes, guidance/glossary, and canonical compatibility,
  architecture, qualification and plan resolutions. The refreshed spec/map match
  the context read for #19. Testing Decisions already approve candidate/path
  traces and CLI byte/status observation. No new product flag or testing seam.
- All seven original untracked local files remain byte-for-byte preserved and
  excluded from commits. No production C++ source, installation behavior,
  indexing resource, planning-map or resolved-decision change.

## Delivered bridge and independent checks

`tests/fixtures/ordered_replay.py` is a development-only bridge used by the
fixture-sized Python model. It accepts a fully prepared candidate sequence,
validates full SHA-1 IDs and duplicate-free subsequence membership, and invokes
exactly one selected Git process for a nonempty sequence:

```text
git --no-pager log --no-walk=unsorted --stdin -S<needle> --
stdin: full object IDs, one per line, in current traversal order
```

The needle is one direct byte argument. The replay has no `--all`, never sorts
by timestamps, and never concatenates independently formatted results. Empty
candidates return successful empty bytes without launching Git. This guarded
path is necessary because an empty `--stdin` can implicitly search HEAD.

All candidate preparation/validation precedes replay. Fixture subprocesses
capture complete stdout in RAM, intentionally acceptable only for these tiny
experiments. This is neither the bounded C++ builder nor a production stdout,
resource, eligibility, cancellation or mutation protocol.

The #19 independent tree-snapshot association oracle and Git `-S` identity
oracle remain intact. For each replay case, the extended harness additionally:

1. Checks `rev-list --all` scope/order against independent unfiltered
   `log --all --format=%H --`, with no duplicates. Reference matching identities
   must appear in the same traversal order.
2. Derives a duplicate-free ordered candidate subsequence, retaining the
   original filter candidates separately from deliberate extra candidates.
3. Captures exact reference `git --no-pager log --all -S<needle> --` stdout/status.
4. Requires one replay process for nonempty candidates or zero for empty ones,
   and compares raw output bytes/status with that unchanged reference. Traces
   retain path, scope, coverage, candidates, reference matches, invocation count,
   raw commands/stdin/output/status and associations.

## Exercised gate cases

Six new checks join #19's five checks in the same approved trace suite:

- **Actual pruning and formatting:** retain root/deletion matches while excluding
  a known nonmatching covered commit. Repeat with all scope IDs as conservative
  extra candidates. Both produce identical reference bytes through one replay,
  with no fallback. Separately concatenating one-commit Git outputs differs,
  demonstrating why a single formatting session matters.
- **One candidate / nonempty zero matches:** a one-commit matching history replays
  once; `aaaa` keeps its `aaa` blob's commit as a harmless false positive, then
  Git emits no matches. Candidate and match are different concepts.
- **Empty guard and unborn repository:** the actual reference on the unborn
  fixture succeeds with empty scope/stdout (status 0). A real zero-match needle
  in a nonempty repository yields no candidates and launches no replay. A
  separate guard challenge passes an empty prepared sequence with a needle
  known to match HEAD; the guard still launches nothing. The deliberately
  unguarded Git command searches HEAD and emits output, retaining the hazard.
- **Traversal:** tied branch timestamps, a child dated earlier than its parent,
  multiple refs to one commit, a tag, and a new detached-only HEAD commit.
  A linear skew-dated case proves timestamp sorting would reorder matches;
  branched cases use Git's actual order rather than imposing a topology rule.
- **Merges/gitlinks/coverage:** two-parent and octopus merges; gitlink addition,
  update and deletion, including a needle in Git's synthesized submodule
  representation. Freeze model coverage, then really fetch an unrelated older
  branch from a local donor repository and add a new unindexed commit. All
  in-scope always-check and unindexed commits survive for matching and zero-match
  needles, with reference output preserved.
- **Scope changes:** move refs among covered IDs; retain history through a tag;
  delete the last retaining tag; then move to unrelated history with the same
  commit count and delete the old branch. Stored out-of-scope IDs disappear
  from the candidate sequence. No formatted covered/uncovered streams are merged.

## Actual checks and investigations

- C++20 Release build (`cmake --build build`) passed with unchanged `pk` source.
  The replay test first failed because its bridge module did not exist; after
  implementation the focused pruning/formatting test passed.
- One auxiliary ordering assertion initially assumed a shared parent must follow
  a skew-dated child across branches. Direct Git's reference and replay output
  agreed while that assertion failed. Inspecting the recorded identities/output
  isolated a test assumption error, not an architectural replay failure. Kept
  the raw byte oracle unchanged; added a separate linear skew case and removed
  the invented branched topology rule. Retained the initial observation in the
  archive. No required case was removed or weakened.
- Four temporary defective bridges were rejected with status 1: implicit-HEAD
  launch, replacing `--no-walk=unsorted` with date-sorted `--no-walk`, adding
  `--all`, and splitting formatting across per-commit sessions. These are
  deliberate negative controls, not failed product runs or gate failures.
- Full implemented suite: **2/2 CTest entries, 29/29 Python checks, no skips**:
  18 existing CLI checks plus 11 containment/replay checks. Includes all prior
  byte/status/cancellation/descriptor behavior. macOS process checks ran with
  required local access. Recorded full-suite duration: 25.73 seconds (fixture
  observation, not a performance claim).
- Actual environment remains macOS 15.7.4 / 24G517, arm64, inherited PATH selecting
  `/usr/bin/git` (Apple Git 2.39.5 / Apple Git-154), Apple Clang 17.0.0, CMake 4.1.2.
  No Git substitution, Linux preparation, or newly qualified profile.
- Compiled and ran the C++ subsequence demonstration below. Replayed this
  repository's complete traversal for `std::string`; captured stdout matched
  the reference with `cmp`. This all-candidates demonstration exercises the
  protocol; the fixture evidence above separately proves real pruning.
- [evidence/ticket-20.json.gz](evidence/ticket-20.json.gz) retains all 29 records,
  exact byte arguments/stdin/stdout/stderr/statuses, effective config and refs,
  selected environment, source/Git/binary hashes, candidate traces, full CTest
  log, initial red/ordering observations, four defect probe results and their
  driver, and demonstration source/output. Archive round trip and source hashes
  were verified. #19's archive stays a historical source-pinned record.

No eligible fundamental containment/replay failure was observed. Passing the
small gate permits later investigation; it neither completes milestone 2 nor
qualifies acceleration. Full dependency/eligibility, bounded extraction,
allocation/integrity, mutation/cancellation/publication and generated-history
qualification remain pending in their assigned tickets.

## Runnable demonstrations

Run focused gate checks and retain their actual candidate IDs/byte streams:

```sh
python3 tests/candidate_containment.py --evidence-dir build/evidence/candidate-containment \
  Containment.test_replay_prunes_and_preserves_one_formatting_session \
  Containment.test_replay_empty_guard_and_unborn_outcome \
  Containment.test_replay_branch_order_with_tied_and_skewed_dates -v
ctest --test-dir build --output-on-failure -V
```

Inspect exercised paths and process counts:

```sh
python3 - <<'PY'
import json
from pathlib import Path
p = Path('build/evidence/candidate-containment/test_replay_prunes_and_preserves_one_formatting_session.json')
for trace in json.loads(p.read_text())['traces']:
    print(trace['path'], 'replay processes:', trace['replay_invocations'])
    print('scope:', trace['scope'])
    print('filter:', trace['filter_candidates'])
    print('replay:', trace['candidates'])
    print('matches:', trace['reference_matches'])
PY
```

One process keeps Git's formatting state, including inter-commit separators.
`--stdin` supplies revision identities, `--no-walk` prevents ancestor traversal,
and `=unsorted` preserves their supplied order. `--all` belongs only to current
scope/reference discovery. This disposable all-candidates example compares bytes
on this repository without changing it:

```sh
demo=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-replay.XXXXXX")
git rev-list --all > "$demo/ids"
git --no-pager log --all '-Sstd::string' -- > "$demo/reference"
git --no-pager log --no-walk=unsorted --stdin '-Sstd::string' -- \
  < "$demo/ids" > "$demo/replay"
cmp "$demo/reference" "$demo/replay"
```

A branch is a name pointing to a commit; commit timestamps do not define graph
order. The current traversal decides ordering and scope; coverage decides which
commits may be filtered. A moved branch can expose old uncovered history, and a
deleted last ref can remove stored history from current scope.

In C++, a vector preserves sequence order while a set answers membership in its
own key order. Iterate traversal and test candidate membership; do not emit IDs
by iterating the set or sorting timestamps. This small C++20 demonstration prints
`z-child` then `a-parent`, regardless of their lexical order:

```sh
demo=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-subsequence.XXXXXX")
cat > "$demo/subsequence.cpp" <<'CPP'
#include <iostream>
#include <set>
#include <string>
#include <vector>
int main() {
    const std::vector<std::string> traversal{"z-child", "a-parent", "unrelated"};
    const std::set<std::string> candidates{"a-parent", "z-child"};
    for (const auto& commit : traversal) {
        if (candidates.contains(commit)) {
            std::cout << commit << '\n';
        }
    }
}
CPP
/usr/bin/clang++ -std=c++20 -Wall -Wextra -Wpedantic \
  "$demo/subsequence.cpp" -o "$demo/subsequence"
"$demo/subsequence"
```

`const auto&` borrows each vector string for that loop iteration, avoiding a
copy. The strings/containers own their storage and release it on scope exit
(RAII). These ordinary allocating containers illustrate ordering, not the
production indexing memory budget. The fixture bridge likewise remains Python;
no premature production C++ helper framework was introduced.

## Review and handoff

Applied the code-review skill with independent parallel reviewers against
`8296457bafa48f065d98a58387bff734304c201e...9881e46` (one implementation commit).

### Standards

Pass: **0 documented violations, 0 actionable smell findings**. The reviewer
independently ran all 11 containment/replay checks, verified archive source
hashes and 29 records, and checked whitespace.

### Spec

Pass: **0 findings**. The reviewer independently ran all 11 checks and verified
all required gate cases, the four rejected defective bridges, raw source-pinned
evidence and the full-suite 29/29 pass. The retained initial ordering observation
shows reference/replay already agreed; correcting the auxiliary assertion did
not weaken the reference oracle.

Standards: 0 findings; Spec: 0 findings; neither axis has an outstanding issue.
Only review/handoff documentation changed after review. `git diff --check` and
all seven preserved-local-file hashes passed. Only #19 and #20 are included in
this draft PR.
Do not mark ready, merge, close either issue, or start another ticket here.

Next ticket, **not started**:
[#21 — Investigate effective dependencies for eligibility](https://github.com/alifrahman2023/pickaxe/issues/21).
#22's macOS publication investigation also remains pending. Product search
continues complete Git fallback with no force-acceleration option.
