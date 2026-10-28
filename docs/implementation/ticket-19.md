# Ticket #19 implementation evidence

Scope: [M2 / T04 — Establish candidate containment on tiny histories](https://github.com/alifrahman2023/pickaxe/issues/19),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Executed on 2026-10-28. This is containment feasibility evidence; acceleration
remains disabled in the product. No production C++ change is needed here.

## Baseline and approved seams

- Ticket branch: `ticket/19-candidate-containment`.
- Starting/review baseline: `b76a046b383afb3b7fc7652813fdc87e1d9268ec`.
  PR #50 is merged at that commit. #19 was open/unassigned, has zero open native
  blockers, and was claimed for the owner; its #18 blocker is closed.
- Read #19, full #15, map #1 Notes, repository tracker/domain/triage guidance,
  glossary, and canonical compatibility, architecture, qualification and plan
  comments linked by #19. No applicable ADR exists. The map and resolved
  decisions are unchanged.
- The specification's Testing Decisions approve CLI byte/status observation,
  development-only candidate/traversal/path traces, and deterministic helper
  controls. TDD used the candidate-trace seam: the first complete-side test
  failed because the model was absent, then passed with the implementation.
  Further fixtures extended that same seam; three defect probes check sensitivity.
- Preserved untracked `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GLOSSARY.md`, and
  `docs/agents/` byte-for-byte and excluded them from commits.

## Delivered model and independent evidence

`tests/fixtures/candidate_model.py` is an explicitly unbounded Python model.
It holds complete helper output, trees, blob bytes, sets and mappings in memory.
It never enters `pk`, writes an index resource, or claims the production memory
budget. Later tickets own the C++ accounted builder, external sorting and format.

The model enumerates full recursive raw old/new sides using `diff-tree`, full
object IDs and NUL-delimited paths. Explicit helper flags disable relative/path
restriction, rename pairing, external diff, text conversion, and ignored
submodules. Roots compare against the empty tree. One `cat-file --batch` request
reads each distinct associated blob once, checks object identity/type/length and
framing, and processes seven-byte chunks carrying their last two bytes.

Distinct trigram postings intersect **blob IDs**, then associations union commit
IDs. Current `rev-list --all` scope retains matching associations, always-check
commits and every unindexed commit. Stored out-of-scope IDs do not enter the
trace. This is containment/scope evidence, not qualification of traversal order.

Two independent oracles challenge this model:

1. Full `ls-tree -r -z --full-tree` snapshots compare pathname/mode/object-ID
   entries with the parent (or empty root). They derive exact expected blob
   associations and gitlink classifications without reusing raw change records
   or trigram logic. Merges are independently classified by parent count.
2. `git --no-pager log --all --format=%H -S<needle> --` supplies matching commit
   identities, retaining effective search settings. Formatting identities is a
   diagnostic oracle, not the exact-output replay oracle owned by #20.

Five checks cover:

- Roots, old/new contents, count increases, deletion-only matches; a known
  nonmatching covered commit is excluded while all three matches are retained.
  A genuine empty candidate sequence is observed. No replay invocation is made;
  proving its empty-input behavior belongs to #20. One/two-byte model queries
  explicitly require whole-search Git fallback.
- Binary NUL/invalid bytes, symlink contents, pure rename, copy, rename with edits,
  regular/symlink type change, executable mode, deletion, spaces/tabs/newlines in
  filenames, and subdirectory extraction with a match outside that directory.
  Hostile `diff.relative`, `diff.renames`, `diff.ignoreSubmodules` and
  `diff.external` settings cannot suppress internal associations. Effective
  config is unchanged before/after extraction; reference settings stay intact.
- Two blobs `qwer` and `erty` collectively cover the trigrams of `qwerty`, but
  neither passes individually. Repeated trigrams (`aaaa`), dispersed order
  (`abc--bcd--cde`) and pure rename permit conservative candidates. Needles cross
  seven-byte chunk boundaries, including UTF-8 bytes split between chunks.
- Two-parent/octopus merges; gitlink addition/update/deletion; an actual reference
  match for Git's synthesized `Subproject commit <full-ID>` content; retention
  of all five always-check commits even for a zero-match needle. Internal
  extraction remains complete with ignored submodules configured. An older
  unindexed branch is retained regardless of date. Deleting eligible refs and
  moving HEAD excludes stored history that is no longer in scope.
- A configured text converter creates `converted-only` absent from raw blobs.
  Reference Git selects matches while the raw model has no candidates. This
  expected unsupported-setting observation invalidates the raw proof and
  requires whole-search fallback. It is not an eligible containment pass and
  does not qualify an eligibility detector. The working CLI already falls back.

## Conditional no-false-negative argument

For a covered sole-parent/root commit under qualified raw-content semantics,
Git selecting a literal count change means the needle occurs on at least one
complete compared side. Every distinct needle trigram occurs in that blob, so
that blob survives intersection and its complete association retains the commit.
Merges, gitlink changes and unindexed commits bypass exclusion. Current scope
limits all candidates. Repetitions, order and counts can create false positives;
Git must still verify them. Verification cannot recover an excluded match.

The argument depends on complete enumeration/object reads, qualified repository
interpretation, and exclusion of applicable text conversion or other settings
that invalidate raw-content semantics. Tiny passing fixtures establish neither
all such dependencies nor an eligibility implementation. No eligible fundamental
containment failure was observed. Ordered replay must pass separately before
substantial dependent index construction proceeds.

## Runnable Git and C++ demonstrations

Run the complete model or one focused case:

```sh
python3 tests/candidate_containment.py --evidence-dir build/evidence/candidate-containment -v
python3 tests/candidate_containment.py Containment.test_blob_intersection_repetition_and_chunk_boundaries -v
python3 tests/candidate_containment.py Containment.test_merges_gitlinks_unindexed_and_out_of_scope -v
```

Inspect actual candidate/match IDs, rather than only a pass message:

```sh
python3 - <<'PY'
import json
from pathlib import Path
p = Path('build/evidence/candidate-containment/test_complete_sides_and_deletions.json')
for trace in json.loads(p.read_text())['traces']:
    print(bytes.fromhex(trace['needle_hex']), trace['path'])
    print('candidates:', trace['candidates'])
    print('matches:   ', trace['reference_matches'])
PY
```

A **commit** names a tree plus parents and metadata. A **tree** maps names and
modes to objects; recursive trees describe directories. A **blob** owns file
bytes, not a filename. Identical bytes share a blob ID, so a blob can associate
with several paths/commits. These commands inspect this repository without
changing it:

```sh
git cat-file -p HEAD
git ls-tree -r HEAD
git cat-file blob HEAD:src/main.cpp
```

In C++, `std::string` can own arbitrary blob bytes, including NUL when constructed
with an explicit length. C-style argument strings terminate at NUL, which is why
`pk` cannot receive NUL in a needle. A `std::set<std::string>` owns copied trigram
bytes and deduplicates them; that alone proves neither occurrence count nor
order. Compile this disposable demonstration with the selected compiler:

```sh
demo=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-bytes.XXXXXX")
cat > "$demo/bytes.cpp" <<'CPP'
#include <iostream>
#include <set>
#include <string>
int main() {
    const std::string blob("\0aaaa", 5);
    std::set<std::string> trigrams;
    for (std::size_t i = 0; i + 2 < blob.size(); ++i) {
        trigrams.insert(blob.substr(i, 3));
    }
    std::cout << "blob bytes=" << blob.size()
              << ", unique trigrams=" << trigrams.size() << '\n';
}
CPP
/usr/bin/clang++ -std=c++20 -Wall -Wextra -Wpedantic "$demo/bytes.cpp" -o "$demo/bytes"
"$demo/bytes"
# Expected, and observed: blob bytes=5, unique trigrams=2
```

The demonstration uses ordinary allocating containers and is not the budgeted
builder. RAII destroys their owned storage on scope exit. In the actual CLI,
`std::string` owns needle/argument bytes until `execv` replaces the process with
Git. Build and run that unchanged C++ boundary:

```sh
cmake --build build
./build/pk search 'std::string'
git --no-pager log --all '-Sstd::string' --
```

Git branches are movable names for commits, not copies of files. The ticket
branch begins at the recorded commit; new commits extend it without advancing
`main`. Compare only this ticket against its fixed starting point:

```sh
git status --short
git log b76a046b383afb3b7fc7652813fdc87e1d9268ec..HEAD --oneline
git diff b76a046b383afb3b7fc7652813fdc87e1d9268ec...HEAD
```

Untracked files are outside commits until explicitly staged; switching the
branch preserved the owner's local guidance. Staging named ticket files keeps
that local work out of the PR.

## Checks and retained evidence

- Actual host: macOS 15.7.4 / 24G517, arm64; inherited PATH selects `/usr/bin/git`,
  Apple Git 2.39.5 (Apple Git-154). Apple Clang 17.0.0
  (`clang-1700.0.13.5`); CMake 4.1.2. No Git substitution or Linux preparation.
- C++20 Release configure/build passed. Focused containment tests passed.
- Three temporary defective models were rejected with status 1: omitting old
  sides, losing chunk overlap, and intersecting associated commits across blobs.
  These are expected test failures, not product failures or architecture flaws.
- Full implemented CTest suite: **2/2 entries, 23/23 Python checks, no skips**,
  including all 18 unchanged CLI byte/status/cancellation/descriptor checks.
  Existing macOS process/PTY tests ran with required local access. Production
  installation is unaffected; no installation behavior changed.
- The C++ byte demonstration compiled and printed the expected result above.
- Raw evidence: `evidence/ticket-19.json.gz` retains all five new fixture records,
  18 baseline records, full command/input/output/status bytes, effective config,
  refs, selected environment, source/Git/binary hashes, candidate/association/
  coverage/match traces, CTest log and mutation results. Hex and gzip are storage
  encodings; oracle matching uses live Git. Paths identify transient fixture
  repositories; run the scripts to recreate them. The archive round trip and
  source hashes were checked.

```sh
ctest --test-dir build --output-on-failure -V
gzip -dc docs/implementation/evidence/ticket-19.json.gz > /tmp/pickaxe-ticket-19-evidence.json
```

## Review and handoff

Applied the code-review skill with independent parallel Standards and Spec
reviewers against the recorded starting commit, initially reviewing `00706b4`.

### Standards

Pass: **0 documented violations, 0 actionable smell findings**. The reviewer
independently reran the five containment checks and verified the archive's 23
records, source hashes and whitespace check.

### Spec

Initial review found **2 fixture evidence gaps**, with no candidate-model
correctness failure: the UTF-8 character was inside one chunk, and rename/edit
were separate commits. Corrected the fixture to put `é` at offsets 6–7 across a
seven-byte boundary and renamed/edited the same file in one commit. Focused
checks and all three defect probes passed; the full suite and archive were
regenerated. Follow-up Spec review through `29d3bdd`: **0 outstanding findings**.
The reviewer independently reran both affected checks and verified all 23 records,
source hashes, defect probes and full-suite pass. Follow-up Standards review:
**0 documented violations, 0 actionable smells** through the same commit.

Final axis totals: Standards 0 findings; Spec 0 outstanding findings (2 initial
fixture gaps resolved). Only review/handoff documentation changed after review.
`git diff --check` and all seven preserved-local-file hashes passed.

Only #19 is implemented. Draft PR preparation does not mark it ready, merge it,
or close the issue. Next ticket, **not started**:
[#20 — Pass the ordered Git replay feasibility gate](https://github.com/alifrahman2023/pickaxe/issues/20).
Replay/order/format equivalence, early eligibility/publication investigations,
production bounded extraction, all later qualification fixtures/generator,
resource/publication audits, measurements and Linux qualification remain pending.
