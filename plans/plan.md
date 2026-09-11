# `pk` — implementation plan

Trigram inverted index over commit diffs, so `git log -S <string>` becomes a
posting-list intersection plus exact verification.

C++20 · CMake + Ninja · GoogleTest · macOS (dev) + Linux (CI/bench).
Background on *why* each choice was made: [context/notes.md](../context/notes.md).

---

## 1. Contract

Output byte-identical to `git log --all -S <needle>` — same commits, same order.

- **Filter is conservative.** Every occurrence that changes a count lies wholly inside
  a `+`/`-` line (proof: §2.1), so the commit has all of the needle's trigrams. The one
  exception is content inside a binary filepair, which the textual diff never shows and
  the pickaxe searches anyway (spikes.md S6); those commits are always candidates.
- **Verification is exact.** Git itself is the verifier (§2.2).

**Bail out** (print a notice, exec real `git log -S`) when: needle < 3 bytes · needle
contains `\n` · every trigram of the needle is a stopword · index missing/stale ·
unsupported flag (`-i`, `--pickaxe-regex`, `-G`).

---

## 2. Design decisions

### 2.1 Why indexing only changed lines is sound

A needle with no `\n` cannot span a line boundary. Occurrences inside *unchanged* lines
are present in both preimage and postimage, so they cancel. Therefore any per-file count
change is caused by an occurrence lying entirely within an added or removed line — which
is exactly what we index. No false negatives.

**The argument assumes the diff shows everything that changed, and for binary files it
does not.** `git diff -U0` prints `Binary files ... differ` with no content lines, while
`diffcore_pickaxe` reads the blob itself and matches inside it regardless (measured,
spikes.md S6). Indexing the textual diff alone therefore *would* miss a needle that only
occurs in binary content. The fix is not to index it — `--text` on a vendored PNG is one
enormous line of noise — but to recognise the marker while parsing and add the commit's
ordinal to the always-candidate list (§4). Verification then decides. On git.git this
affects 35 of 64,022 non-merge commits, 0.05%.

### 2.2 Verification = one batched `git log --no-walk`

Do **not** reimplement pickaxe counting for v1. After intersection we hold ~40 candidate
SHAs. Feed them to git in a single subprocess (verified — spikes.md S2):

```
printf '%s\n' <shas...> | git log --stdin --no-walk -S <needle> --format=%H
```

Git applies its own pickaxe to exactly those commits and prints the survivors. Correct by
construction — no per-file delta logic, no rename edge cases, no overlapping-match bugs.
**Pass no diff options to this call.** In particular not `--no-renames`: with it, git
reports a commit that merely moved the needle between files, and plain `git log -S` does
not (spikes.md S4). The index is built one way and verified the other on purpose.
One process, not 40. Feed the SHAs in descending-ordinal order and git's output is already
in `git log --all -S` order (§2.4), so print it straight through, enriched from the commit
table.

> Phase-2 optimisation (only after `--verify` is green): count in-process from the `-U0`
> diff as `Δ_file = occ(+ lines) − occ(− lines)`, show commit iff any `Δ_file ≠ 0`.

### 2.3 Index with `--no-renames`, verify with git's defaults

Rename detection turns a "delete + add" pair into one content diff, so its changed-line
set is a **subset** of the `--no-renames` set. Indexing without renames is therefore a
superset filter that is valid for rename-following queries, and it is cheaper to build.
The header records the build settings; the reader rejects an index whose settings cannot
serve the query.

### 2.4 Ordinals and output order

`ordinal` = position in **reverse** `git rev-list --all` order (0 = oldest). Append-only, so
`pk update` never renumbers anything. Postings store ascending ordinals, delta-varint.

**Ordering is git's job** (verified, spikes.md S3). `git log --stdin --no-walk -S` sorts its
output by commit date descending and uses **input order as the tie-break**. So feeding
candidates in descending-ordinal order, which is `git rev-list --all` order, reproduces
`git log --all -S` ordering exactly, ties included. No `display_rank` array, no re-deriving
git's priority-queue semantics, nothing to recompute on update.

Residual risk: a commit added by a later `pk update` that is *older* than commits already
indexed gets a high ordinal and is fed out of position. It still sorts correctly by date;
only an exact timestamp tie against another matching commit could misorder it. Cover this
case in `--verify`.

### 2.7 Staleness: the index is never required to be fresh

A working-tree edit changes nothing. `pk` indexes commits, and so does `git log -S`. Only
new commits matter, and history is append-only.

So a query **covers the gap with git** instead of demanding a fresh index:

1. at query start, spawn `git rev-list --all --not <indexed tips>` (the header stores the tips);
2. intersect postings while that runs, so the subprocess cost overlaps with real work;
3. union the gap commits into the candidate set;
4. verify everything in one batched call (§2.2).

Results are therefore correct whatever the index's age. `pk update` is pure optimisation: it
moves commits out of the "git checks these live" set into the "the index filters these" set.

**Update policy: never require the user to think about it.** A hook the user has to install
is friction, and a tool that silently returns stale answers is worse. Gap cost is about one
git diff per unindexed commit, so:

| gap | behaviour |
|---|---|
| 0 | nothing |
| small (start the threshold at ~1000 commits) | cover live in the verification call; cost is invisible |
| large | update inline first, one-line notice on stderr, then answer |
| no index at all | notice on stderr, `exec` real `git log -S` so the user still gets an answer |
| history rewritten | notice, `exec` real `git log -S`, suggest `pk index` |

Queries stay read-only on the common path; only the large-gap branch writes, under a lock
file so concurrent invocations cannot corrupt a segment. Local commits keep the gap in the
single digits and never trigger a write; the gap grows mainly from `git pull`. `pk update`
remains a command for CI and scripting, and `pk hook install` is *offered* in `pk index`'s
output but never installed silently, since it would clobber husky / pre-commit setups.

Refinement once v1 works: do the large-gap update in a detached background process so no
query ever pays for it.

**Updates append a segment, they never rewrite.** Postings are contiguous per trigram, so
appending one ordinal to trigram T shifts every byte after it: a full rewrite of the entire
blob, seconds of I/O, impossible on a query path. Instead `pk update` writes a new small
segment file; a query intersects each segment and unions the candidates; `pk compact` merges
segments back down. This is the standard LSM / Lucene arrangement.

History *rewrites* (`rebase`, `--amend`, force-push, `gc` pruning unreachable commits)
invalidate ordinals rather than extending them. Detect by the stored tips no longer being
reachable, and require a full `pk index`.

### 2.5 Build is an external sort

Measured on git.git: 3.0 kB of keys per commit (spikes.md S5), so ~1.5 GB at 500k commits
and ~3.9 GB at 1.3M — less than the 6 GB this section originally assumed, but still past
the point where holding every key in RAM is sensible.

Commits are split into **chunks of contiguous ordinals**. Each chunk produces one run of
`u64 key = (tri << 32) | ordinal`, radix-sorted and spilled to a temp file. Because chunk
ordinal ranges are disjoint and ascending, the final merge for a given trigram is a plain
**ordered concatenation** of the runs — no comparison merge needed inside a trigram.
Streams straight into the delta-varint writer. Memory stays at one chunk per worker.

**Cut chunks on a key budget, not a commit count.** Commits span 3.0 kB of keys on average
and 400 kB at the worst, a 3,000× spread, so a fixed number of commits per chunk makes peak
memory unpredictable. Fill the buffer until it reaches its byte limit and cut there. The
ordinal ranges stay contiguous and disjoint, which is all the concatenation argument
above needs.

### 2.6 Merge commits

**Resolved empirically** ([context/spikes.md](../context/spikes.md) S1): default
`git log -S` produces no diff for a merge and therefore never reports one — not even an
"evil merge" whose resolution introduces content present in neither parent. So `pk`
**does not index merges and does not report them.** This reproduces a real blind spot in
`git log -S`; document it in the README rather than "fixing" it, because the contract is
byte-identical output. `--first-parent` / `-m` are non-goals.

---

## 3. Layout

```
CMakeLists.txt  CMakePresets.json  .clang-format  .clang-tidy  .gitignore
src/
  main.cpp                 # subcommand dispatch and exit codes only
  pk/
    cli.{hpp,cpp}          # argv -> Options; in the library so it is testable
    version.hpp/.cpp       # git describe, baked in at configure time
    subprocess.{hpp,cpp}   # posix_spawn + pipe, streaming stdout reader
    git.{hpp,cpp}          # rev_list_all, log_stream, verify_batch
    diff_parser.{hpp,cpp}  # NUL-delimited -U0 stream -> CommitRecord
    trigram.hpp            # extraction + per-commit dedupe (bitset)
    varint.hpp             # LEB128 encode/decode
    radix_sort.hpp         # LSD u64, 8 bits/pass
    index_format.hpp       # POD header/record structs, magic, version
    index_builder.{hpp,cpp}# chunk -> run -> merge -> serialize
    index_reader.{hpp,cpp} # mmap, directory binary search
    mmap_file.{hpp,cpp}    # RAII mmap
    intersect.{hpp,cpp}    # rarest-first galloping intersection
    query.{hpp,cpp}        # needle -> candidates -> verify -> print
tests/
  unit/                    # one function, no I/O
  integration/             # git_assumptions_test.sh pins the spike findings
  fixtures/make_repo.sh    # synthetic repos: merges, renames, binary, root commit
tools/spike_trigram_stats.py # phase-1 measurement harness; `pk stats` replaces it
bench/run.sh
docker/Dockerfile
plans/plan.md  context/notes.md  context/spikes.md  README.md
```

`libpk` is a static library holding everything under `src/pk/`; `pk` is a thin executable
and the tests link the same library. Never put logic in `main.cpp` — it cannot be tested.

**Dependencies:** GoogleTest only, via CMake `FetchContent`. Arg parsing is hand-rolled
(~80 lines; the surface is tiny). No libgit2 in v1.

---

## 4. Index file format

Single little-endian mmap-able file at `.git/pk-index`. All section offsets are absolute
and 8-byte aligned.

```
header       magic "PKIX" · version · flags(no_renames, merges_indexed) · context_lines
             commit_count · trigram_count · section offsets · stopword_count
             indexed ref tips (staleness check + gap query) · always-candidate list · repo path
directory    u32 tri[N]  ·  u64 post_off[N+1]  ·  u32 post_count[N]   (SoA, tri ascending)
postings     varint(first_ordinal), then varint(delta) per subsequent ordinal
commit_table ordinal -> { u8 oid[20], i64 time, u32 author_off, u32 subject_off }  (40 B)
strings      NUL-terminated authors + subjects
stopwords    sorted u32[]
```

Directory lookup is a binary search over `tri[]` (≤24 probes, 18 on git.git's measured
249,005 distinct trigrams; a query has ~10–30 trigrams, so this is free). A 2^24 direct
table would cost ~200 MB — rejected.

A full index is one file; `pk update` adds `pk-index.1`, `.2`, … segments until `pk compact`.

**Sizing, measured.** Built over git.git's whole history and serialized for real
(spikes.md S5), before any stopword cull:

| | git.git, 85,615 commits |
|---|---|
| distinct trigrams per commit | 373 mean, 129 median, 50,308 worst |
| postings | 32.0M |
| postings on disk | 37.4 MB, at **1.17 B/posting** |
| directory + commit table | 4.0 MB + 3.4 MB |
| **index total** | **44.8 MB**, 14% of the 316 MB pack beside it |
| raw keys during the build | 0.26 GB, 3.0 kB per commit |

Scaling the measured per-commit figures, and taking the ≈25% cull that a >10% stopword
threshold delivers:

| commits | postings | index on disk | raw keys during build |
|---|---|---|---|
| 100k | 37M | ~40 MB | 0.3 GB |
| 500k | 187M | ~190 MB | 1.5 GB |
| 1.3M | 485M | ~500 MB | 3.9 GB |

The right-hand column is why the build is an external sort (§2.5). Re-measure per repo
rather than trusting these across ecosystems: a Java or JavaScript monorepo has different
line lengths and a different trigram curve than git.git's C.

**Is that size acceptable?** On disk yes, in RAM it barely registers. The file is mmap'd and
a query touches only its header, a few directory pages and a few posting lists, so resident
memory stays in the low MB no matter how big the file is. On disk it measured **14% of the
pack sitting next to it** on git.git, better than the quarter this section first guessed. It
is derived data under `.git/`, it is never committed or pushed, and deleting it costs a
rebuild and nothing else.

The real risk is the **build's transient**, not the steady state. Check free space before
starting, honour `--tmpdir`, run the counting pass and cull *before* spilling keys, and clean
up runs in a destructor. If a user is still space-constrained, the stopword cull threshold is
the knob: culling harder shrinks the index and admits more candidates, trading index size for
query time.

**The always-candidate list.** Two kinds of commit go in it instead of being indexed, and
both stay correct because verification still sees them:

- **Dense commits.** One commit importing a vendored tree can contribute millions of
  distinct trigrams, as much as thousands of ordinary commits, while filtering nothing.
  Cap at K distinct trigrams. **K = 10,000**, not the 50k first guessed here: on git.git
  50k catches a single commit, while 10k catches 44 (0.07% of history) holding 2.0% of all
  postings (spikes.md S5).
- **Commits touching a binary filepair.** Their content is invisible to `-U0` and still
  searched by the pickaxe, so indexing cannot see what git will match (spikes.md S6).
  35 commits on git.git, 0.05%.

Both are cheap, and between them they remove the worst of the tail and close the only hole
in §2.1.

---

## 5. Phases

Each phase ends with a green build, green `ctest`, and a committed exit check.

| # | Deliverable | Exit criterion | Est |
|---|---|---|---|
| 0 | Skeleton: CMake, presets, gtest, clang-format, .gitignore, Dockerfile, CI | `cmake --preset dev && cmake --build --preset dev && ctest --preset dev` green | 1.0h |
| 1 | **Spikes** (§7) — all six resolved, S6 found a correctness hole | spikes.md complete; one regression test per finding | 0.5h |
| 2 | `subprocess` + `git` + `diff_parser`; hidden `pk scan` prints stats | commit count on git.git == `git rev-list --all --count` | 2.0h |
| 3 | Trigram extraction, counting pass, stopword selection; `pk stats` | top-50 histogram printed; cull threshold justified | 1.0h |
| 4 | Radix sort, runs, merge, serialize, mmap read-back | round-trip test; `pk index .` on git.git succeeds; size + time reported | 2.0h |
| 5 | Query: lookup, galloping intersect, batched verify, print | `pk --verify -S` matches `git log --all -S` on 50 needles across 3 repos | 2.0h |
| 6 | Parallel build (thread pool over chunks) | ≥4× faster **and** byte-identical index vs single-threaded | 1.5h |
| 7 | `pk update` segment append, gap query (§2.7), `pk compact`, CLI polish | query correct with a deliberately stale index; update+compact == full rebuild | 1.5h |
| 8 | Benchmarks + README | table of §6 filled in with real numbers | 1.5h |

Phases 0–5 are the minimum shippable path. If behind, cut 6 before 8.

---

## 6. Testing

| Layer | What | How |
|---|---|---|
| Unit | varint round-trip, radix sort vs `std::sort`, galloping intersect vs naive, trigram extraction, occurrence counting incl. overlapping (`aaa` in `aaaa`) | GoogleTest, property-style with a seeded RNG |
| Golden | diff parser against checked-in `-U0` fixtures: binary files, mode-only change, root commit, empty file, CRLF, no trailing newline | fixtures in `tests/fixtures/` |
| Integration | `tests/fixtures/make_repo.sh` builds a synthetic repo (merges, renames, binary, root commit) in a temp dir; index it; assert queries | CTest, repo built once per run |
| Differential | `pk --verify -S <needle>` runs both and diffs — **the acceptance criterion** | needle shapes: rare identifier, common word, exactly 3 bytes, punctuation-heavy, zero-hit, all-stopword |
| Sanitizers | ASan+UBSan on all tests; TSan on the parallel build | separate CMake presets, run in CI |
| Determinism | parallel index bytes == single-threaded index bytes | phase 6 exit check |

Test the failure paths too: corrupt/truncated index, wrong magic, version mismatch, index
older than HEAD, needle shorter than 3 bytes.

---

## 7. Spikes to run first (phase 1)

Answer each with a real command against a real repo; append findings to
[context/spikes.md](../context/spikes.md).

**All resolved.** S1 (merges), S2 (batched `--no-walk` verification) and S3 (ordering) were
answered before phase 1; S4 (renames), S5 (measurement) and S6 landed in it. Each is pinned
by an assertion in `tests/integration/git_assumptions_test.sh`.

Two changed the design rather than confirming it:

- **S6**, which was not on this list, found that the pickaxe searches binary blobs the
  textual diff never shows — a false negative, fixed by the always-candidate list (§2.1, §4).
- **S5** measured the index at roughly a third of the size assumed here, and moved the
  dense-commit cap from 50k to 10k and the stopword cull to >10% of commits (§4).

The numbers behind S5 come from `tools/spike_trigram_stats.py`, which `pk stats` replaces in
phase 3.

---

## 8. Benchmarks

`hyperfine` (`brew install hyperfine`), repos `git`, `linux`, `llvm-project`, on Linux in
Docker for reproducibility. Report **all** baselines, including the unflattering one:

1. `git log -S X` cold, no commit-graph
2. `git log -S X` with `git commit-graph write --reachable --changed-paths`
3. `git log -S X -- <path>` with changed-path filters (git does best here)
4. `pk -S X`

Always print index build time and index size next to the query time. The pitch is
amortisation, not a free lunch.

---

## 9. Distribution

Runtime dependency surface is effectively nil: one binary plus `git` on `PATH`, which every
user of a git tool already has. Nothing installs alongside it. That is what makes the
channels below cheap. Docker is a build and benchmark environment only, never the shipping
vehicle: container startup is 100-500ms against a 30ms query budget, and the tool needs the
user's filesystem. See [notes §14](../context/notes.md).

| Platform | Channel | Notes |
|---|---|---|
| macOS | own Homebrew tap (`brew tap <user>/tap && brew install pk`) | day one; `homebrew-core` later, it has notability requirements |
| Linux | tarball on GitHub Releases | primary channel; the same Homebrew formula also works |
| Linux | AUR `PKGBUILD`, Nix flake | cheap to add, community-maintainable |
| Windows | WSL only | native port = replacing `posix_spawn`/`mmap`/`poll` with Win32. Non-goal |

**Release mechanism.** Tag → GitHub Actions matrix builds `macos-arm64`, `macos-x86_64`,
`linux-x86_64`, `linux-arm64` → uploads tarballs plus `SHA256SUMS` to the Release. The
formula points at those URLs. Same workflow file as CI, different trigger.

**The glibc trap** (Linux; this one will bite you). A binary built on Ubuntu 24.04 will not
run on Debian 12, because glibc symbol versions are forward-only and the newer build
records newer symbols. Fixes, in order of preference:

1. build release binaries in a container with the **oldest** glibc you intend to support;
2. link `-static-libstdc++ -static-libgcc` so the C++ ABI is not also a variable;
3. fully static against musl (Alpine builder) if you want to stop thinking about it.

**Also required:** `install(TARGETS pk RUNTIME DESTINATION ...)` with `GNUInstallDirs` so
`cmake --install build/release` works, and a version string baked in from `git describe` so
bug reports identify a build. macOS note: a directly downloaded binary is Gatekeeper-
quarantined and refuses to run; Homebrew installs are not. Codesign and notarize only if
you ship direct downloads.

---

## 10. Non-goals for v1

`-G <regex>` · libgit2 · SIMD intersection · needles containing `\n` · `-i` /
`--pickaxe-regex` · `--first-parent` / `-m` · path or author pre-filters · Windows.
