#!/usr/bin/env bash
# Builds the synthetic repos the integration and spike-regression tests run against.
#
#   make_repo.sh <dest-dir>
#
# Every commit gets a fixed author, committer and timestamp, so the repos are
# byte-reproducible and the tests can assert on exact SHAs and exact ordering.
# The user's global and system git config are ignored for the same reason.
set -euo pipefail

dest=${1:?usage: make_repo.sh <dest-dir>}
mkdir -p "$dest"
dest=$(cd "$dest" && pwd)

export GIT_CONFIG_GLOBAL=/dev/null
export GIT_CONFIG_NOSYSTEM=1
export GIT_AUTHOR_NAME='pk fixture'
export GIT_AUTHOR_EMAIL='fixture@pk.invalid'
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"
export TZ=UTC

now=1700000000  # advanced by one minute per commit

new_repo() {
  rm -rf "$dest/$1"
  mkdir -p "$dest/$1"
  cd "$dest/$1"
  git init -q -b main
}

# commit <message> [epoch-seconds]   — omit the timestamp to advance the clock
commit() {
  local stamp=${2:-}
  if [ -z "$stamp" ]; then
    now=$((now + 60))
    stamp=$now
  fi
  GIT_AUTHOR_DATE="$stamp +0000" GIT_COMMITTER_DATE="$stamp +0000" \
    git commit -q --no-verify -m "$1"
}

# ---------------------------------------------------------------- evil-merge
# S1: both sides edit the same line, and the resolution introduces a string that
# exists in neither parent. `git log -S` still reports nothing.
new_repo evil-merge
printf 'base line\n' > f.txt
git add f.txt
commit 'base'
printf 'main edit\n' > f.txt
git add f.txt
commit 'main edit'
git checkout -q -b side HEAD~1
printf 'side edit\n' > f.txt
git add f.txt
commit 'side edit'
git checkout -q main
git merge --no-commit side >/dev/null 2>&1 || true
printf 'EVIL_MERGE_ONLY\n' > f.txt
git add f.txt
commit 'merge resolution introduces needle'

# ------------------------------------------------------------------- pickaxe
# S2: one commit adds the needle, a later one removes it. Also carries the diff
# shapes the parser has to survive: binary, mode-only, CRLF, no trailing
# newline, empty file, and a second root commit on an orphan branch.
new_repo pickaxe
printf 'int main(void) { return 0; }\n' > c.c
git add c.c
commit 'c1 initial'
printf 'int main(void) { return 0; }\nstatic const int ZLIB_BUF_MAX = 1;\n' > c.c
git add c.c
commit 'c2 adds needle'
printf 'int main(void) { return 1; }\nstatic const int ZLIB_BUF_MAX = 1;\n' > c.c
git add c.c
commit 'c3 unrelated change'
printf 'int main(void) { return 1; }\n' > c.c
git add c.c
commit 'c4 removes needle'
printf '\x00\x01\x02\xffZLIB_BUF_MAX\x00' > blob.bin
git add blob.bin
commit 'c5 adds a binary file'
chmod +x c.c
git add c.c
commit 'c6 mode-only change'
printf 'crlf line one\r\ncrlf line two\r\n' > crlf.txt
printf 'no trailing newline' > nonl.txt
: > empty.txt
git add crlf.txt nonl.txt empty.txt
commit 'c7 crlf, missing newline, empty file'
git checkout -q --orphan root2
git rm -rq --cached .
rm -f c.c blob.bin crlf.txt nonl.txt empty.txt
printf 'ROOT_ONLY_NEEDLE\n' > other.txt
git add other.txt
commit 'r1 second root commit introduces needle'
git checkout -q main

# ---------------------------------------------------------------------- ties
# S3: every commit shares one timestamp, so `git log -S` ordering is decided
# entirely by the tie-break. Two branches interleave.
new_repo ties
tie_date=1700100000
printf 'seed\n' > t.txt
git add t.txt
commit 'base' "$tie_date"
for i in 1 2 3 4; do
  printf 'TIE_NEEDLE %s\n' "$i" > t.txt
  git add t.txt
  commit "main$i" "$tie_date"
done
git checkout -q -b side main~4
for i in 5 6 7; do
  printf 'TIE_NEEDLE %s\n' "$i" > t.txt
  git add t.txt
  commit "side$i" "$tie_date"
done
git checkout -q main

# -------------------------------------------------------------------- rename
# S4: a rename that also edits content. The needle moves between files without
# its count changing, which is the case where --no-renames and git's default
# rename detection disagree.
new_repo rename
{
  printf 'line one\n'
  printf 'line two\n'
  printf 'RENAMED_NEEDLE lives here\n'
  printf 'line four\n'
  printf 'line five\n'
  printf 'line six\n'
} > old.txt
git add old.txt
commit 'adds old.txt containing the needle'
git mv old.txt new.txt
sed -i.bak 's/line four/line four, edited/' new.txt && rm -f new.txt.bak
git add new.txt
commit 'renames old.txt to new.txt and edits one line'

echo "$dest"
