#!/usr/bin/env bash
# Regression tests for the spike findings in context/spikes.md.
#
# These assert on *git's* behaviour, not pk's. Every one of them is load-bearing:
# the index format, the verification strategy and the output ordering are all
# built on top of them. If a future git release changes one, this goes red before
# the differential tests start producing mystery diffs.
set -uo pipefail

here=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
make_repo="$here/../fixtures/make_repo.sh"
work=$(mktemp -d "${TMPDIR:-/tmp}/pk-spikes.XXXXXX")
trap 'rm -rf "$work"' EXIT

"$make_repo" "$work" >/dev/null

failures=0
check() {  # check <description> <expected> <actual>
  if [ "$2" = "$3" ]; then
    printf 'ok   - %s\n' "$1"
  else
    printf 'FAIL - %s\n       expected: %q\n       actual:   %q\n' "$1" "$2" "$3"
    failures=$((failures + 1))
  fi
}

# Signed changed lines of one revision, hunk bodies only. The +++/--- file
# headers sit before the first @@, so tracking hunk state excludes them.
changed_lines() {  # changed_lines <repo> <rev> [git diff args...]
  local repo=$1 rev=$2
  shift 2
  git -C "$repo" show -U0 --format= --no-color "$@" "$rev" | awk '
    /^diff --git/ { inhunk = 0; next }
    /^@@/         { inhunk = 1; next }
    inhunk && /^[+-]/ { print }
  ' | sort
}

# --------------------------------------------------------- S1: merge commits
em="$work/evil-merge"
merge=$(git -C "$em" rev-parse main)

check 'S1 default git log -S never reports a merge, even an evil one' \
  '' "$(git -C "$em" log --all -S EVIL_MERGE_ONLY --format=%H)"

check 'S1 -m does report it, which is why -m is a non-goal' \
  "$merge" "$(git -C "$em" log --all -m -S EVIL_MERGE_ONLY --format=%H | sort -u)"

check 'S1 a merge has no -U0 diff body to index' \
  '' "$(git -C "$em" log --no-walk -p -U0 --format= "$merge")"

# ------------------------------------------------ S2: batched --no-walk verify
px="$work/pickaxe"
for needle in ZLIB_BUF_MAX ROOT_ONLY_NEEDLE; do
  truth=$(git -C "$px" log --all -S "$needle" --format=%H)
  batched=$(git -C "$px" rev-list --all |
            git -C "$px" log --stdin --no-walk -S "$needle" --format=%H)
  check "S2 batched --no-walk reproduces git log --all -S $needle, in order" \
    "$truth" "$batched"
done

check 'S2 a root commit is verified like any other candidate' \
  "$(git -C "$px" rev-parse root2)" \
  "$(git -C "$px" log --all -S ROOT_ONLY_NEEDLE --format=%H)"

check 'S2 feeding a non-matching candidate does not produce output' \
  '' "$(git -C "$px" rev-parse main | git -C "$px" log --stdin --no-walk \
        -S NEEDLE_THAT_IS_NOWHERE --format=%H)"

# ------------------------------------------------------------- S3: ordering
ties="$work/ties"
truth=$(git -C "$ties" log --all -S TIE_NEEDLE --format=%H)
rev_order=$(git -C "$ties" rev-list --all |
            git -C "$ties" log --stdin --no-walk -S TIE_NEEDLE --format=%H)

check 'S3 all tie-repo commits really do share one timestamp' \
  '1' "$(git -C "$ties" log --all --format=%ct | sort -u | wc -l | tr -d ' ')"

check 'S3 rev-list order reproduces git log --all -S under total date ties' \
  "$truth" "$rev_order"

forward=$(git -C "$ties" rev-list --all |
          git -C "$ties" log --stdin '--no-walk=unsorted' -S TIE_NEEDLE --format=%H)
reverse=$(git -C "$ties" rev-list --all | tail -r 2>/dev/null || true)
if [ -z "$reverse" ]; then
  reverse=$(git -C "$ties" rev-list --all | tac)
fi
reversed_out=$(printf '%s\n' "$reverse" |
               git -C "$ties" log --stdin '--no-walk=unsorted' -S TIE_NEEDLE --format=%H)

check 'S3 --no-walk=unsorted preserves input order verbatim' \
  "$(printf '%s\n' "$forward" | tail -r 2>/dev/null || printf '%s\n' "$forward" | tac)" \
  "$reversed_out"

# ---------------------------------------------------------------- S4: renames
rn="$work/rename"
rename_commit=$(git -C "$rn" rev-parse main)
default_lines=$(changed_lines "$rn" "$rename_commit")
norename_lines=$(changed_lines "$rn" "$rename_commit" --no-renames)

check 'S4 --no-renames changed lines are a superset of the default ones' \
  '' "$(comm -13 <(printf '%s\n' "$norename_lines") <(printf '%s\n' "$default_lines"))"

check 'S4 and a strict superset here, so the filter admits extra candidates' \
  'yes' \
  "$([ "$default_lines" != "$norename_lines" ] && echo yes || echo no)"

# The consequence for pk: indexing with --no-renames makes this commit a
# candidate, and git's default rename detection then drops it. Verification must
# therefore NOT pass --no-renames, or pk would report a commit git does not.
check 'S4 default rename detection does not report a needle that only moved' \
  '' "$(git -C "$rn" log --no-walk -S RENAMED_NEEDLE --format=%H "$rename_commit")"

check 'S4 --no-renames does report it, so the index filter is the superset side' \
  "$rename_commit" \
  "$(git -C "$rn" log --no-walk --no-renames -S RENAMED_NEEDLE --format=%H "$rename_commit")"

# --------------------------------------------------------------- S6: binaries
bin_commit=$(git -C "$px" log --all --format=%H --grep='c5 adds a binary file')

check 'S6 a binary filepair contributes no lines to a -U0 diff' \
  '' "$(changed_lines "$px" "$bin_commit")"

check 'S6 yet the pickaxe searches the blob and matches it' \
  "$bin_commit" \
  "$(git -C "$px" log --no-walk -S ZLIB_BUF_MAX --format=%H "$bin_commit")"

check 'S6 the -U0 diff marks the filepair binary, which is the signal to catch' \
  '1' \
  "$(git -C "$px" show -U0 --format= "$bin_commit" | grep -c '^Binary files')"

# Grepped raw rather than through changed_lines(): BSD awk truncates a record at
# the first NUL, which is also a reminder that the real parser must be
# NUL-safe and never touch these bytes with C string functions.
check 'S6 --text is what exposes that content as diff lines' \
  'yes' \
  "$(git -C "$px" show -U0 --format= --text "$bin_commit" |
     LC_ALL=C grep -aq 'ZLIB_BUF_MAX' && echo yes || echo no)"

printf '\n'
if [ "$failures" -eq 0 ]; then
  printf 'all spike assumptions hold\n'
  exit 0
fi
printf '%d assumption(s) no longer hold\n' "$failures"
exit 1
