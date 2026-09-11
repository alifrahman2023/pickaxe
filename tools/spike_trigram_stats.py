#!/usr/bin/env python3
"""Phase-1 measurement harness for spike S5 (plans/plan.md §7).

Streams `git log -U0` over a repo's whole history and reports the numbers the
index format has to be sized against: distinct trigrams per commit, the trigram
frequency curve that sets the stopword cull, and how many commits carry content
the textual diff does not show.

Throwaway: superseded by `pk stats` in phase 3. Kept because it is the evidence
behind the numbers written into context/spikes.md.

    tools/spike_trigram_stats.py <repo> [--limit N]
"""

import argparse
import subprocess
import sys

import numpy as np

MARKER = b"\x01"
TRIGRAM_SPACE = 1 << 24
NEWLINE = 10


def hunk_body_lines(header: bytes) -> int:
    """Line count of a -U0 hunk body, from `@@ -a,b +c,d @@`.

    Counted parsing is the only correct way to walk the stream: a removed line
    whose text starts with `-- ` renders as `--- ...` and is indistinguishable
    from a file header otherwise.
    """
    try:
        spans = header.split(b"@@")[1].split()
        total = 0
        for span in spans:
            _, _, count = span[1:].partition(b",")
            total += int(count) if count else 1
        return total
    except (IndexError, ValueError):
        return -1


def trigrams(chunks: list[bytes]) -> np.ndarray:
    """Distinct trigrams over the given lines, none spanning a line boundary."""
    if not chunks:
        return np.empty(0, dtype=np.uint32)
    buf = np.frombuffer(b"\n".join(chunks), dtype=np.uint8)
    if buf.size < 3:
        return np.empty(0, dtype=np.uint32)
    a, b, c = buf[:-2], buf[1:-1], buf[2:]
    keys = (a.astype(np.uint32) << 16) | (b.astype(np.uint32) << 8) | c
    inside = (a != NEWLINE) & (b != NEWLINE) & (c != NEWLINE)
    return np.unique(keys[inside])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("repo")
    ap.add_argument("--limit", type=int, default=0, help="stop after N commits")
    ap.add_argument("--dense-cap", type=int, default=50_000)
    args = ap.parse_args()

    # --reverse so ordinals ascend exactly as the index assigns them, and no
    # --no-merges: a merge simply has no -U0 diff body (spike S1), so it
    # contributes nothing while still consuming an ordinal.
    cmd = ["git", "-C", args.repo, "log", "--all", "--reverse", "--no-renames",
           "-U0", "--no-color", "--format=" + MARKER.decode() + "%H %P"]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, bufsize=1 << 20)
    assert proc.stdout is not None

    doc_freq = np.zeros(TRIGRAM_SPACE, dtype=np.uint32)
    last_ordinal = np.full(TRIGRAM_SPACE, -1, dtype=np.int64)
    varint_edges = np.array([1 << 7, 1 << 14, 1 << 21, 1 << 28], dtype=np.int64)
    per_commit: list[int] = []
    lines: list[bytes] = []
    commits = binary_commits = empty_commits = merges = 0
    binary_empty = posting_bytes = 0
    binary_seen = False
    is_merge = False
    changed_lines = changed_bytes = 0
    pending = 0  # unconsumed hunk-body lines
    malformed = 0

    def flush() -> None:
        nonlocal commits, binary_commits, empty_commits, binary_seen, merges
        nonlocal binary_empty, posting_bytes, is_merge
        ordinal = commits
        commits += 1
        if is_merge:
            merges += 1
        distinct = trigrams(lines)
        per_commit.append(int(distinct.size))
        if distinct.size:
            doc_freq[distinct] += 1
            gaps = ordinal - last_ordinal[distinct]
            posting_bytes += int(
                (np.searchsorted(varint_edges, gaps, side="right") + 1).sum())
            last_ordinal[distinct] = ordinal
        elif not is_merge:
            empty_commits += 1
            if binary_seen:
                binary_empty += 1
        if binary_seen:
            binary_commits += 1
        lines.clear()
        binary_seen = False
        is_merge = False

    started = False
    for raw in proc.stdout:
        line = raw.rstrip(b"\n")
        if pending > 0:
            pending -= 1
            if line[:1] in (b"+", b"-"):
                body = line[1:]
                lines.append(body)
                changed_lines += 1
                changed_bytes += len(body)
            continue
        if line.startswith(MARKER):
            if started:
                flush()
            started = True
            is_merge = len(line[1:].split()) > 2  # "<sha> <parent>..."
            if args.limit and commits >= args.limit:
                break
            continue
        if line.startswith(b"@@"):
            pending = hunk_body_lines(line)
            if pending < 0:
                malformed += 1
                pending = 0
            continue
        if line.startswith(b"Binary files") or line.startswith(b"GIT binary patch"):
            binary_seen = True
    if started and (lines or not args.limit or commits < args.limit):
        flush()

    proc.stdout.close()
    proc.wait()

    counts = np.array(per_commit, dtype=np.int64)
    postings = int(counts.sum())
    present = doc_freq[doc_freq > 0]
    order = np.argsort(doc_freq)[::-1]

    def pct(p: float) -> int:
        return int(np.percentile(counts, p))

    non_merge = commits - merges
    print(f"repo                    {args.repo}")
    print(f"commits (all, ordinals) {commits:,}")
    print(f"  merges, not indexed   {merges:,}  ({merges / commits:.2%})")
    print(f"commits (non-merge)     {non_merge:,}")
    print(f"  no indexable content  {empty_commits:,}  "
          f"({empty_commits / non_merge:.2%} of non-merge)")
    print(f"  touch a binary file   {binary_commits:,}  "
          f"({binary_commits / non_merge:.2%} of non-merge)")
    print(f"  binary and nothing e. {binary_empty:,}")
    print(f"  over dense cap {args.dense_cap:,}  "
          f"{int((counts > args.dense_cap).sum()):,}")
    print(f"malformed hunk headers  {malformed:,}")
    print(f"changed lines           {changed_lines:,}")
    print(f"changed bytes           {changed_bytes:,}")
    print()
    print("distinct trigrams per commit")
    for label, value in (("mean", int(counts.mean())), ("median", pct(50)),
                         ("p90", pct(90)), ("p99", pct(99)), ("p99.9", pct(99.9)),
                         ("max", int(counts.max()))):
        print(f"  {label:<8} {value:>12,}")
    print()
    print(f"distinct trigrams overall  {present.size:,} of {TRIGRAM_SPACE:,} possible")
    print(f"total postings             {postings:,}")
    print(f"  raw build keys (8 B)     {postings * 8 / 1e9:.2f} GB")
    print()
    directory = present.size * 16          # u32 tri + u64 off + u32 count
    commit_table = commits * 40            # oid, time, author_off, subject_off
    print("measured index size (delta-varint, not an estimate)")
    print(f"  postings                 {posting_bytes / 1e6:>8.1f} MB  "
          f"({posting_bytes / postings:.2f} B/posting)")
    print(f"  directory                {directory / 1e6:>8.1f} MB")
    print(f"  commit table             {commit_table / 1e6:>8.1f} MB")
    print(f"  total                    "
          f"{(posting_bytes + directory + commit_table) / 1e6:>8.1f} MB")
    print()
    print("dense-commit cap: commits above K, and the postings they hold")
    print(f"  {'K':>10} {'commits':>10} {'postings':>14} {'share':>8}")
    for cap in (100_000, 50_000, 20_000, 10_000, 5_000):
        mask = counts > cap
        held = int(counts[mask].sum())
        print(f"  {cap:>10,} {int(mask.sum()):>10,} {held:>14,} "
              f"{held / postings:>7.1%}")
    print()
    print("stopword cull: trigrams appearing in more than X% of commits")
    print(f"  {'threshold':>10} {'trigrams':>10} {'postings held':>15} {'share':>8}")
    for share in (50, 20, 10, 5, 2, 1):
        cut = commits * share / 100
        mask = doc_freq > cut
        held = int(doc_freq[mask].sum())
        print(f"  {share:>9}% {int(mask.sum()):>10,} {held:>15,} {held / postings:>7.1%}")
    print()
    print("top 30 trigrams by commit frequency")
    for key in order[:30]:
        k = int(key)
        text = bytes((k >> 16 & 0xFF, k >> 8 & 0xFF, k & 0xFF))
        print(f"  {text!r:<12} {int(doc_freq[k]):>9,}  {doc_freq[k] / commits:>6.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
