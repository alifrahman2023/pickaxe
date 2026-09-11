# Spike findings

Empirical answers to the open questions in [plans/plan.md](../plans/plan.md) §7.
Each was run against a purpose-built synthetic repo. Re-run them as tests in phase 1.

---

## S1 — `git log -S` does **not** report merge commits (resolved)

Built an "evil merge": both branches edit `f.txt` differently, the conflict is resolved to
`EVIL_MERGE_ONLY`, a string present in **neither** parent.

```
*   f79265a merge resolution introduces needle
|\
| * 559e60a side edit
* | 5053602 main edit
|/
* 51b629e base
```

```console
$ git log --all -S EVIL_MERGE_ONLY --format='%h %s'
            # <- empty
$ git log --all -m -S EVIL_MERGE_ONLY --format='%h %s'
f79265a merge resolution introduces needle
f79265a merge resolution introduces needle     # once per parent
$ git log --no-walk -p -U0 <merge>
f79265a...  # header only, no diff body
```

**Conclusion.** Default `git log -S` produces no diff for a merge, so a merge is never
reported — not even for content that exists in no parent. Plan §2.6 stands: **do not index
merges, do not report them.** This is a real blind spot in `git log -S` itself, and `pk`
reproduces it deliberately because the contract is byte-identical output. Note it in the
README rather than "fixing" it. `-m` is a non-goal (it also duplicates the commit per parent).

## S2 — `git log --stdin --no-walk -S` filters the given commits (resolved)

Verification strategy of plan §2.2 depends on this.

```console
$ git log --all -S ZLIB_BUF_MAX --format='%h %s'      # truth
c32a997 c4 removes needle
a2a4139 c2 adds needle

$ git rev-list --all | git log --stdin --no-walk -S ZLIB_BUF_MAX --format='%h %s'
c32a997 c4 removes needle
a2a4139 c2 adds needle
```

**Conclusion.** Git applies the pickaxe to exactly the commits fed on stdin and prints only
the survivors. One subprocess verifies the whole candidate set, and correctness is git's
problem, not ours.

Caveats to still handle in code:
- feed SHAs via `--stdin` (not argv) to dodge `ARG_MAX`, and `poll()` the pipes (notes §10);
- `--no-walk` orders by commit date with input order as the tie-break, which is exactly what
  we want; feed candidates in rev-list order (see S3);
- confirm behaviour once more on a repo where a candidate is a root commit.

---

## S3 — ordering: git sorts by date, input order breaks ties (resolved)

Forced every commit in a branched repo to an identical timestamp, so ties are unavoidable:

```console
$ git log --all -S NEEDLE --format='%h %s'        # truth
10e3f50 main4 / 2e3e2bb side7 / 53fd459 main3 / 8756ec8 side6 / ...

$ git rev-list --all | git log --stdin --no-walk -S NEEDLE --format='%h %s'
10e3f50 main4 / 2e3e2bb side7 / 53fd459 main3 / 8756ec8 side6 / ...   # identical

$ git rev-list --all | sort -R | git log --stdin --no-walk -S NEEDLE  # shuffled input
8756ec8 side6 / 6445c69 side5 / 53fd459 main3 / cf0ce77 main1 / ...   # scrambled
```

With *distinct* dates, shuffled input still came out correctly date-ordered.
`--no-walk=unsorted` preserves input order verbatim.

**Conclusion.** `--no-walk` sorts by commit date descending and uses **input order as the
tie-break**. Feed candidates in `git rev-list --all` order (= descending ordinal) and git
reproduces `git log --all -S` ordering exactly, ties included. Plan §2.4 drops the
`display_rank` array entirely, which is also what makes append-only `pk update` viable.

---

## S4 — `--no-renames` changed lines are a strict superset (resolved)

`old.txt` holds six lines including `RENAMED_NEEDLE`; the next commit `git mv`s it to
`new.txt` and edits one *other* line, giving 77% similarity.

```console
$ git show -U0 --format= HEAD                 # default, rename detected
diff --git a/old.txt b/new.txt
similarity index 77%
@@ -4 +4 @@ RENAMED_NEEDLE lives here
-line four
+line four, edited

$ git show -U0 --format= --no-renames HEAD    # delete + add, 12 lines
+line one  +line two  +RENAMED_NEEDLE lives here  +line four, edited  +line five  +line six
-line one  -line two  -RENAMED_NEEDLE lives here  -line four          -line five  -line six
```

Two changed lines under the default, twelve without renames, and the two are among the
twelve. Plan §2.3 confirmed: indexing with `--no-renames` yields a superset.

The interesting half is what the pickaxe then does with it:

```console
$ git log --all -S RENAMED_NEEDLE --format='%h %s'              # git's default
6b566a9 adds old.txt containing the needle                      # rename commit absent

$ git log --all --no-renames -S RENAMED_NEEDLE --format='%h %s'
ac379ff renames old.txt to new.txt and edits one line           # rename commit present
6b566a9 adds old.txt containing the needle
```

With rename detection on, the needle's count is unchanged across the single rename
filepair, so the commit is not reported. With `--no-renames` there are two filepairs, a
delete where the count goes 1→0 and an add where it goes 0→1, and either alone is a
change.

**Conclusion.** The superset is strict in both directions that matter: pk's filter will
nominate the rename commit, and git's verification will drop it. That is the intended
arrangement, but it pins down an implementation rule — **the verification call must not
pass `--no-renames`**, or pk would print a commit `git log --all -S` does not.

## S5 — measured on git.git (resolved)

85,615 commits, whole history, via `tools/spike_trigram_stats.py`. Not estimates.

| | |
|---|---|
| commits, all (each takes an ordinal) | 85,615 |
| merges, contributing nothing (S1) | 21,593 · 25.2% |
| non-merge commits indexed | 64,022 |
| changed lines / bytes | 8.05M · 258 MB |
| distinct trigrams overall | 249,005 of 16.7M possible |
| total postings | 32.0M |

Distinct trigrams per commit are far lower than the plan's ~750–1500 guess:

| mean | median | p90 | p99 | p99.9 | max |
|---|---|---|---|---|---|
| 373 | 129 | 821 | 4,263 | 8,074 | 50,308 |

Serialized size, delta-varint'd, measured rather than assumed:

| section | size | |
|---|---|---|
| postings | 37.4 MB | 1.17 B/posting |
| directory | 4.0 MB | 16 B × 249k trigrams |
| commit table | 3.4 MB | 40 B × 85.6k commits |
| **total** | **44.8 MB** | **14% of the 316 MB pack beside it** |

Raw keys during the build come to 0.26 GB, not the 6 GB the plan's model implies for this
size. Extrapolating the measured 3.0 kB of keys per commit: ~1.5 GB at 500k commits,
~3.9 GB at 1.3M. The external sort earns its keep on linux and llvm-project; a
single in-RAM pass stays viable well past 100k commits.

**Stopword cull.** No trigram appears in more than half of all commits.

| appears in > | trigrams | postings held |
|---|---|---|
| 20% of commits | 126 | 8.6% |
| **10% of commits** | **585** | **25.3%** |
| 5% of commits | 1,488 | 42.0% |
| 2% of commits | 3,686 | 60.6% |

Cull at **>10%**: it discards 585 of 249,005 trigrams (0.2%) and a quarter of the whole
index. Nothing of value is lost — a trigram in 10% of commits leaves 6,400 candidates and
so filters almost nothing once intersected with a selective one. The top of the curve is
exactly what you would guess: `if `, ` re`, ` in`, ` co`, `ed `, `git`, `\t\t\t`.

**Dense-commit cap.** The plan's K = 50,000 catches one commit in all of git.git.

| K | commits above | postings held |
|---|---|---|
| 50,000 | 1 | 0.2% |
| **10,000** | **44** | **2.0%** |
| 5,000 | 497 | 10.7% |

Set **K = 10,000**: 2% of the index removed in exchange for 44 commits (0.07%) that are
always candidates.

**Chunk buffer.** 3.0 kB of keys per commit on average, but 400 kB for the worst commit —
a 3,000× spread. Sizing a chunk by commit count therefore makes peak memory
unpredictable. Size it by **key budget** instead: fill until the buffer reaches its byte
limit, then cut the chunk there. Ordinal ranges stay contiguous and disjoint, which is all
the ordered-concatenation argument in §2.5 needs.

## S6 — the pickaxe reads binary blobs; `-U0` does not show them (new, and it matters)

Not on the original list. Found while testing S2 against a fixture that adds a binary file
whose bytes happen to contain the needle.

```console
$ git show -U0 --format= 95a7af5              # what an index build would see
diff --git a/blob.bin b/blob.bin
new file mode 100644
Binary files /dev/null and b/blob.bin differ  # no content lines at all

$ git log --no-walk -S ZLIB_BUF_MAX --format='%h %s' 95a7af5
95a7af5 c5 adds a binary file                 # but git matches it anyway
```

`diffcore_pickaxe` counts occurrences in the blob contents and never consults the textual
diff, so binary-ness is irrelevant to it. An index built from `-U0` output has a **false
negative** for any needle that occurs only inside binary content — a direct breach of the
byte-identical contract, and the one hole in §2.1's soundness argument, which assumes the
diff shows everything that changed.

`--text` would expose the content as diff lines, so indexing it is possible. It is also
not worth it: a single vendored PNG becomes one enormous line of trigram noise.

Measured on git.git: **35 of 64,022 non-merge commits touch a binary filepair — 0.05%.**

**Conclusion.** Detect the `Binary files ... differ` marker while parsing, and put that
commit's ordinal in the always-a-candidate list the dense-commit cap already needs
(plan §4). Verification then decides, exactly as it does for dense commits. Cost on
git.git is 35 extra SHAs in one batched call, which is unmeasurable. Plan §2.1 and §4
updated.

---

## Regression tests

All six findings are pinned by `tests/integration/git_assumptions_test.sh`, which builds
its repos with `tests/fixtures/make_repo.sh` and runs under `ctest`. They assert on *git's*
behaviour, so they go red on a git release that changes any of it — before the differential
tests start producing diffs nobody can explain.

One harness note worth keeping: BSD `awk` truncates a record at the first NUL byte, which
silently swallowed the binary content in the first draft of the S6 test. The real parser
must stay NUL-safe and never hand these bytes to a C string function.
