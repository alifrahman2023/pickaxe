# `pk`

A trigram inverted index over commit diffs, so `git log -S <string>` becomes a posting-list
intersection plus an exact verification pass.

The contract is strict: **output byte-identical to `git log --all -S <needle>`** — same
commits, same order. The index is only ever a filter. Git itself does the verifying, so a
wrong answer would have to be git's.

> **Status: phase 0 of 8.** The skeleton builds, the test suite is green, and the CLI
> parses. No indexing or querying is implemented yet — every subcommand says which phase
> it lands in. See [plans/plan.md](plans/plan.md).

## How it works

1. **Index** every added and removed line of every non-merge commit by trigram. A needle
   with no newline cannot span a line boundary, and occurrences in unchanged lines cancel
   between preimage and postimage, so changed lines are all that can move a count. The
   filter is therefore conservative with no false negatives.
2. **Query** intersects the posting lists of the needle's trigrams, rarest first, leaving a
   few dozen candidate commits out of hundreds of thousands.
3. **Verify** feeds those candidates to git in one batch:
   `git log --stdin --no-walk -S <needle>`. Git applies its own pickaxe and prints the
   survivors, already in the right order.

A stale index is never an error. A query asks git for the commits the index has not seen
yet and folds them into the same verification call, so the answer is correct whatever the
index's age.

## Build

Needs CMake 3.24+, Ninja, and a C++20 compiler.

```sh
cmake --preset dev          # configure
cmake --build --preset dev  # build
ctest --preset dev          # test
```

Presets: `dev` (Debug), `asan` (ASan + UBSan, the one to develop against), `tsan`,
`release`. Build trees live under `build/<preset>/` and are disposable.

## A known blind spot, inherited on purpose

`git log -S` produces no diff for a merge commit and so never reports one — not even an
"evil merge" whose conflict resolution introduces content present in neither parent.
`pk` reproduces this exactly rather than fixing it, because the contract is byte-identical
output. Measured in [context/spikes.md](context/spikes.md) S1.

## Not in v1

`-G <regex>` · `-i` · `--pickaxe-regex` · needles containing a newline · `--first-parent`
and `-m` · path or author pre-filters · Windows (WSL works).

## Design

[plans/plan.md](plans/plan.md) is the implementation plan and the source of truth.
[context/notes.md](context/notes.md) records why each choice was made, and
[context/spikes.md](context/spikes.md) holds the empirical answers the plan leans on.
