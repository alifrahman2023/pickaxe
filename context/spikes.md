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

## Still open

- **S4** — confirm `--no-renames` changed lines ⊇ default changed lines for a
  rename-with-edit.
- **S5** — measure distinct trigrams per commit and the frequency curve on git.git, to size
  the stopword cull and the chunk buffer.
