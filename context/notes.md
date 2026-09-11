# Notes for a first serious C++ project

Companion to [plans/plan.md](../plans/plan.md). Nothing here is `pk`-specific policy —
it's the background you need to read the plan and not get stuck. Skim it once, come back
to sections when a phase hits them.

---

## 1. The mental model of a C++ build

Unlike Python or Go, C++ has no built-in project system. Three separate things happen:

1. **Preprocess** — `#include` literally pastes a header's text into your `.cpp`.
2. **Compile** — each `.cpp` becomes one `.o` object file, independently. A `.cpp` plus
   everything it includes is a *translation unit*. The compiler sees nothing else.
3. **Link** — all `.o` files (plus libraries) are stitched into one executable. This is
   where "undefined reference to `foo`" comes from: you *declared* `foo` in a header but
   never *defined* it in any `.cpp`.

Consequences you will hit:

- Headers (`.hpp`) hold declarations: what exists. Sources (`.cpp`) hold definitions: what
  it does. Put `#pragma once` at the top of every header so double-inclusion is harmless.
- Anything defined *in a header* and included by two `.cpp` files gets defined twice →
  linker error. Escape hatches: mark it `inline`, make it a `template`, or move it to a
  `.cpp`. Small functions in headers should be `inline`.
- Changing a header recompiles every `.cpp` that includes it. Keep headers thin; include
  `<vector>` in the header only if the header's declarations actually need it.

**A build system's whole job** is to know which `.cpp` files exist, which flags to use,
and what to relink. That's CMake.

---

## 2. CMake, presets, and the two commands you'll actually type

CMake is a *generator*: it reads `CMakeLists.txt` and writes real build files (Ninja or
Make), which then do the work. So there are always two steps — configure, then build.

`CMakePresets.json` exists so you don't memorise flag soup. With presets defined:

```sh
cmake --preset dev            # configure (only after changing CMakeLists.txt)
cmake --build --preset dev    # build (after editing code)
ctest --preset dev            # run tests
```

**Out-of-source builds:** everything generated lands in `build/`, which is gitignored and
disposable. If the build ever behaves inexplicably, `rm -rf build` and reconfigure. That
fixes a surprising share of problems and costs nothing.

### A starter `CMakeLists.txt`

```cmake
cmake_minimum_required(VERSION 3.24)
project(pk LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)          # -std=c++20, not -std=gnu++20
set(CMAKE_EXPORT_COMPILE_COMMANDS ON)  # writes build/compile_commands.json

# --- the library: all real logic lives here ------------------------------
add_library(pklib
  src/pk/subprocess.cpp src/pk/git.cpp src/pk/diff_parser.cpp
  src/pk/index_builder.cpp src/pk/index_reader.cpp src/pk/mmap_file.cpp
  src/pk/intersect.cpp src/pk/query.cpp)
target_include_directories(pklib PUBLIC src)
target_compile_options(pklib PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
find_package(Threads REQUIRED)
target_link_libraries(pklib PUBLIC Threads::Threads)

# --- the executable: thin --------------------------------------------------
add_executable(pk src/main.cpp)
target_link_libraries(pk PRIVATE pklib)

# --- tests ------------------------------------------------------------------
include(FetchContent)
FetchContent_Declare(googletest
  GIT_REPOSITORY https://github.com/google/googletest.git
  GIT_TAG        v1.15.2)          # pin a tag, never a branch
FetchContent_MakeAvailable(googletest)

enable_testing()
add_executable(pk_tests tests/unit/varint_test.cpp tests/unit/trigram_test.cpp)
target_link_libraries(pk_tests PRIVATE pklib GTest::gtest_main)
include(GoogleTest)
gtest_discover_tests(pk_tests)
```

Things worth noticing:

- **`PUBLIC` vs `PRIVATE`.** `PUBLIC` on `pklib`'s include dir means anything linking
  `pklib` also gets `src/` on its include path — that's why tests can `#include
  "pk/varint.hpp"`. `PRIVATE` flags don't propagate. Use `PRIVATE` unless you need
  propagation.
- **`compile_commands.json`** is what clangd (the VS Code C++ language server) reads for
  autocomplete and errors. Symlink it to the project root: `ln -s build/dev/compile_commands.json .`
- **`FetchContent`** downloads and builds a dependency as part of your build. For one or
  two deps this beats vcpkg/Conan — no extra tool to install. Always pin an exact tag.
- **`-Wconversion`** catches silent narrowing (`size_t` → `uint32_t`), which is exactly
  the bug class a binary index format invites. It's noisy at first; keep it anyway.

### A starter `CMakePresets.json`

Define at minimum: `dev` (Debug, `-O0 -g`), `asan` (Debug + `-fsanitize=address,undefined`),
`tsan` (`-fsanitize=thread`), `release` (`-O2 -g`, `NDEBUG`). Set `"generator": "Ninja"`
and `"binaryDir": "build/${presetName}"` in each so the four build trees coexist.

**Install Ninja** (`brew install ninja`) — you don't have it. It's dramatically faster
than Make for incremental builds and it's what everyone uses.

---

## 3. Why a library plus a thin `main.cpp`

You cannot `#include` an executable. If parsing logic lives in `main.cpp`, no test can
reach it and you're stuck testing by running the binary and grepping stdout — slow,
flaky, and it can't reach edge cases.

So: **all logic in `pklib`; `main.cpp` only parses argv and calls into it.** Both `pk` and
`pk_tests` link `pklib`. This one structural decision is most of what makes the test plan
in §6 of the plan possible.

---

## 4. Tests, and what "green" means

GoogleTest gives you `TEST(SuiteName, CaseName) { EXPECT_EQ(a, b); }`. `EXPECT_*` records
a failure and continues; `ASSERT_*` aborts the test case (use it when continuing would
crash, e.g. after a null check). `gtest_discover_tests` registers each case with CTest, so
`ctest` runs them and prints a pass/fail summary.

Four kinds of test appear in the plan, and they are not interchangeable:

- **Unit** — one function, no I/O. `varint_encode` then `varint_decode` returns the input,
  for 10,000 random values. Fast enough to run on every save.
- **Golden/fixture** — a checked-in input file and its expected parse. This is how you pin
  down `git diff -U0` weirdness (binary files, mode-only changes, missing trailing
  newline) without needing a repo at test time.
- **Integration** — a script builds a real tiny git repo in a temp dir; you index and
  query it. Slower, catches wiring bugs unit tests can't.
- **Differential** — run `pk` and `git log -S` and diff the output. For a tool whose whole
  contract is "identical to git", this *is* the specification. Everything else is scaffolding
  that helps you debug when this one goes red.

A useful habit: when you find a bug, write the failing test *first*, watch it fail, then
fix it. It proves the test actually exercises the bug.

---

## 5. Sanitizers — the single highest-value tool here

C++ will happily let you read past the end of a buffer and keep going with garbage. A
sanitizer is a compiler flag that instruments the program to catch that at the moment it
happens, with a stack trace.

| Flag | Catches | Cost |
|---|---|---|
| `-fsanitize=address` (ASan) | out-of-bounds reads/writes, use-after-free, leaks | ~2× slower |
| `-fsanitize=undefined` (UBSan) | signed overflow, bad shifts, misaligned loads, invalid enum values | small |
| `-fsanitize=thread` (TSan) | data races between threads | ~10× slower, can't combine with ASan |

Always pair with `-fno-omit-frame-pointer -g` so traces are readable.

This project is exactly the shape sanitizers were built for: manual pointer arithmetic
over an mmap'd file, `string_view`s into a streaming buffer, and a thread pool. **Run the
test suite under ASan+UBSan by default during development**, and TSan once in phase 6.
A crash you can't reproduce is usually memory corruption that ASan would have named
instantly.

---

## 6. Formatting and linting

- **`.clang-format`** — start from `BasedOnStyle: Google`, set `ColumnLimit: 100`. Turn on
  format-on-save in VS Code. Never argue about braces again, and diffs stay meaningful.
- **`.clang-tidy`** — a static analyser. Start with
  `bugprone-*,performance-*,modernize-*,readability-*` and disable individual checks that
  annoy you. It catches real things: accidental copies in range-for loops, `int` where
  `size_t` belongs, missing `override`.

Both read `compile_commands.json`, which is why `CMAKE_EXPORT_COMPILE_COMMANDS` is on.

---

## 7. Docker: what it's for here, and what it isn't

Docker gives you a **reproducible Linux environment**. Two legitimate uses in this project:

1. **CI parity** — you develop on macOS (Apple clang, BSD userland) but CI runs Ubuntu
   (GCC/libstdc++, GNU userland). A Dockerfile lets you reproduce a CI failure locally
   instead of push-and-pray. Real differences bite: `posix_spawn` details, `sysconf`
   values, `std::filesystem` behaviour, and Linux having `MAP_POPULATE` while macOS doesn't.
2. **Benchmarks** — numbers in a README should be from a stated, reproducible machine
   image, not "my laptop with Slack open".

What it is **not** good for here: day-to-day editing and running. Docker Desktop on macOS
runs a Linux VM, and filesystem access to mounted host directories goes through a
translation layer that is *slow* — which is catastrophic for a workload that reads
hundreds of thousands of git objects. If you benchmark inside Docker, keep the repo inside
a **named volume** or clone it inside the container, never on a bind-mounted host path.

A minimal image is enough:

```dockerfile
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential cmake ninja-build git ca-certificates curl \
 && rm -rf /var/lib/apt/lists/*
# hyperfine is not reliably in Ubuntu's default repos; take the released .deb.
ARG HYPERFINE=1.18.0
RUN curl -fsSL -o /tmp/hf.deb \
      "https://github.com/sharkdp/hyperfine/releases/download/v${HYPERFINE}/hyperfine_${HYPERFINE}_amd64.deb" \
 && dpkg -i /tmp/hf.deb && rm /tmp/hf.deb
WORKDIR /work
```

(Pin the version. Check the current tag on the releases page and use `arm64` instead of
`amd64` if you build the image on Apple silicon.)

Then `docker build -t pk-dev docker/ && docker run --rm -it -v pk-cache:/work pk-dev`.

**CI**: one GitHub Actions workflow, matrix over `ubuntu-latest` and `macos-latest`,
steps = configure, build, `ctest`. Add a second job that builds the `asan` preset and runs
the same tests. That's the whole thing; don't over-build it in week one.

---

## 8. C++ ideas this project leans on

**RAII.** A resource (file descriptor, mmap region, child process) is owned by an object;
its destructor releases it. This is *the* C++ idiom — it makes leaks structurally hard
even when exceptions fly. Concretely: `MmapFile` calls `munmap` in `~MmapFile()`, and you
delete its copy constructor (`MmapFile(const MmapFile&) = delete;`) so it can't be copied
into a double-`munmap`. Same for the subprocess wrapper: destructor closes the pipe and
reaps the child, so you never leave zombies.

**`std::string_view` is a borrowed pointer + length.** Using views into a big read buffer
is the reason the parser can be fast — no per-line allocation. It's also the sharpest
footgun in the project: the moment the buffer is refilled or reallocated, every view into
it dangles, and reading it is undefined behaviour that usually *looks like it works*. Rule
for the streaming parser: **never let a `string_view` outlive the buffer refill that
produced it.** Either finish processing a chunk fully before refilling, or copy into a
`std::string`. ASan will catch violations if you build with it — another reason for §5.

**Integer types in a file format.** Use `<cstdint>` types (`uint32_t`, `uint64_t`), never
`int`/`long`, whose sizes vary. Don't `memcpy` a struct straight to disk unless you have
pinned layout: add `static_assert(sizeof(Header) == 128)` and `static_assert(alignof(...))`
so a silent padding change can't corrupt every index built after it. Little-endian only is
fine — say so in the header, and check the magic bytes on load.

**Alignment.** Reading a `uint64_t` from an arbitrary byte offset in an mmap'd buffer is
UB (and slow or fatal on some architectures). Either align sections to 8 bytes — which the
plan does — or read via `memcpy` into a local, which compilers optimise to a single load.

**`const` and references.** Take large parameters as `const std::vector<T>&` to avoid a
copy. A plain `std::vector<T>` parameter copies the whole thing; this is the most common
accidental-slowness bug for newcomers, and `-Wextra` won't warn about it.

---

## 9. The three algorithms, in one paragraph each

**Varint (LEB128).** Store a number in as few bytes as possible: 7 bits of payload per
byte, top bit = "another byte follows". Values under 128 take one byte. Postings are
mostly small *deltas*, so this is where the index-size win comes from.

**Delta encoding.** A posting list is ascending ordinals `[5, 9, 40, 41]`. Store
`[5, 4, 31, 1]` instead — same information, much smaller numbers, so varints stay short.
Decoding is a running sum. The catch: you can no longer jump to element *k* without
decoding everything before it, which is exactly why the intersection below is designed to
stream forward and never seek backwards.

**Galloping (exponential) search.** To intersect a 20-element list with a 2-million-element
one, don't walk the big one. From your current position, probe ahead 1, 2, 4, 8, … until
you overshoot the target, then binary-search that bracket. Cost is O(log(gap)) per element
instead of O(n). Processing lists **rarest-first** matters for the same reason: the
shortest list bounds the answer, so every later list only has to be probed at those few
positions.

**Radix sort (LSD).** Ordinary comparison sorts are O(n log n). Radix sort processes the
key 8 bits at a time — count how many keys have each of 256 possible byte values, turn
counts into offsets, scatter. Eight passes for a `uint64`, each O(n), and you can skip a
pass when a byte position is constant. For hundreds of millions of fixed-width keys this
is a genuine multiple faster than `std::sort` — and it's a nice thing to benchmark and put
in the README.

---

## 10. Subprocesses without deadlocks

You'll spawn `git` a lot. Use `posix_spawn` (simpler and safer than `fork`+`exec`) with a
`posix_spawn_file_actions_t` that redirects the child's stdout to the write end of a pipe.

Rules that prevent the classic hangs:

- **Close the parent's copy of the write end** immediately after spawning. If you don't,
  you never see EOF when the child exits, and your read loop blocks forever.
- **Never write to a child's stdin while it's producing lots of stdout** unless you
  `poll()` both — the child blocks writing stdout because your pipe buffer (64 KB) is
  full, and you block writing stdin. Both wait forever. This matters for the
  `git log --stdin` calls in the plan: if the SHA list is bigger than a pipe buffer, write
  it with `poll()`, or write it to a temp file and pass that.
- **Always `waitpid`** the child and check the exit status. A git error you ignore becomes
  "mysteriously empty index".
- Read with a large buffer (256 KB–1 MB) in a loop until `read()` returns 0.

Budget an hour for this even though it's only ~150 lines. Everyone does.

---

## 11. Debug vs Release, and benchmarking honestly

Debug builds (`-O0`) can be **10–50× slower** than `-O2`. Every performance number must
come from the `release` preset, and `-O2 -g` keeps symbols for the profiler at no runtime
cost. `NDEBUG` (set by Release) disables `assert`, so never put side effects inside an
`assert`.

For measurement use `hyperfine` (`brew install hyperfine` — you don't have it), which
handles warmup runs and reports mean ± σ. Two traps:

- **Page cache.** The second run of anything touching a large repo is much faster because
  the OS cached the files. Report warm-cache numbers and say they're warm; if you claim
  cold numbers, actually drop caches (only feasible on Linux) and say how.
- **Baseline fairness.** The plan lists three git baselines, including
  `git log -S X -- <path>`, which is git's *best* case. Report it. A benchmark table that
  only shows the flattering comparison is the fastest way to lose a reader's trust, and
  it's the one thing reviewers always check.

For profiling: `perf record` / `perf report` on Linux, Instruments (Time Profiler) or
`sample <pid>` on macOS. Profile before optimising — the plan's §10 "SIMD intersection"
stretch goal is listed as *profile first* for exactly this reason.

---

## 12. Git terms used in the plan

| Term | Meaning |
|---|---|
| preimage / postimage | file contents before / after a commit's change |
| hunk | one `@@ -a,b +c,d @@` block of a diff |
| `-U0` | zero lines of context, so every `+`/`-` line is a genuine change |
| pickaxe | git's `-S` implementation, in `diffcore-pickaxe.c` |
| ordinal | *our* integer id for a commit (§2.4 of the plan), not a git concept |
| TREESAME | a commit whose tree matches a parent's; drives history simplification |
| root commit | a commit with no parent; its diff is against the empty tree |
| commit-graph | git's own cached commit metadata file; speeds up traversal, free to generate |

---

## 13. Traps specific to this project

- **`git log -S` walks HEAD, not everything.** `git log -S x` ≠ `git log --all -S x`. Since
  `pk` indexes `--all`, the correct comparison in every test and benchmark is
  `git log --all -S x`. Getting this wrong will make you chase a "bug" that is a spec
  mismatch. This is why the plan states the contract against `git log --all -S`.
- **Overlapping matches.** git counts *non-overlapping* occurrences: `aaa` appears once in
  `aaaa`, not twice. Any hand-rolled counter must match. (Verifying via git — plan §2.2 —
  sidesteps this entirely for v1, which is the point.)
- **All-stopword needles.** If every trigram of the needle was culled, the intersection is
  over nothing and would return *everything*. Detect it and bail to git rather than
  silently doing a full scan or, worse, returning nothing.
- **`std::bitset<16777216>`** is 2 MB — fine per thread, not fine per commit if you
  allocate it fresh each time. Allocate once per worker and clear only the bits you set.
- **Temp files.** The external sort writes runs to disk. Clean them up in a destructor (RAII
  again) so a crashed build doesn't leave gigabytes behind, and put them somewhere with
  actual free space, not `/tmp` on a small volume.
- **Progress output.** A multi-minute index build with no output feels broken. Print a
  progress line to stderr (not stdout) every few seconds, so piping `pk -S` output stays clean.

---

## 14. Dependencies, containers, and shipping a compiled tool

This is where a CLI tool genuinely differs from the full-stack apps you're used to, and the
difference is worth internalising because it changes every downstream decision.

### Interpreted app vs compiled tool

A Node or Python app **ships source**. The runtime and every library must exist on the
target machine at the moment the app runs, so the deployment artifact has to carry them.
That is the entire reason Docker exists for that world: the container *is* the runtime.

A C++ tool **ships a binary**. The compiler consumed the headers, the linker consumed the
libraries, and what comes out the other end is one file with the dependencies already
baked in. At runtime `pk` needs: libc, libc++/libstdc++ (both already on any machine), and
`git` on `PATH`. That's it. GoogleTest never ships. CMake never ships. Nothing is
"installed alongside" it.

So the dependency question splits in two, and people constantly conflate them:

| | Interpreted app | Compiled tool |
|---|---|---|
| Build-time deps | same as runtime deps | compiled away, invisible to users |
| Runtime deps | runtime + all libraries | libc, libstdc++, `git` |
| Deploy artifact | image or source + lockfile | one binary |
| Docker's role | the delivery mechanism | a build/test environment only |

### Three tiers of dependency, and which ones you install by hand

The reason you install `ninja` yourself but not GoogleTest isn't inconsistency. They're
different categories:

1. **Toolchain** (compiler, CMake, Ninja). This is your machine's build environment, not
   your project's dependency. You install Node before `npm install`; same idea. The OS
   package manager owns these: `brew` on macOS, `apt` in the CI image.
2. **Libraries the code links** (GoogleTest). These *are* project dependencies, they're
   pinned in `CMakeLists.txt` via `FetchContent`, and nobody ever installs them manually,
   including you. Cloning the repo and building is enough.
3. **Personal dev tools** (hyperfine, clang-format, lldb, perf). Not needed to build or
   test. They're for you, so they live on your machine, not in the project.

Ninja is tier 1 and is genuinely optional. Drop `"generator": "Ninja"` from the presets and
CMake will generate Makefiles for the `make` that already ships with Xcode Command Line
Tools. Ninja is just noticeably faster at incremental builds, which matters when you'll
rebuild a few hundred times this week.

Now the honest part: **C++ has no npm.** There is no universal, blessed package manager.
vcpkg and Conan exist and both work, but each is another tool to install, another manifest
format, and another failure mode, which is a bad trade when your dependency list is one
test framework. `FetchContent` keeps the whole thing inside CMake at the cost of compiling
GoogleTest once per build tree. Reach for vcpkg only when you're pulling in something with
real transitive deps, like libgit2 in a later version.

### Why Docker is the wrong *deployment* vehicle here specifically

Containerising `pk` would be actively bad, for reasons particular to this tool:

- **Startup cost swamps the work.** `docker run` costs on the order of 100ms to 500ms. The
  query budget is 30ms. The container would be an order of magnitude more expensive than
  the thing you spent a week optimising.
- **It needs your filesystem.** `pk` reads a git repo at an arbitrary path and shells out
  to `git`. Every invocation would need a bind mount and a UID mapping, and on macOS bind
  mounts are slow (notes §7), which again attacks the exact thing being optimised.
- **Nobody expects it.** `git`, `rg`, `fd`, and `jq` are binaries on `PATH`. A dev tool
  that requires a container to run reads as unfinished.

Docker's real jobs in this project are **CI parity** and **reproducible benchmark numbers**,
both build-time. Deployment is a binary in a tarball.

### What "install" looks like on each platform

See plan §9 for the concrete channels. The shape is:

- **macOS**: your own Homebrew tap on day one. A tap is just a GitHub repo named
  `homebrew-tap` containing a Ruby formula. `homebrew-core` comes later and has notability
  requirements (roughly: the project must be established and maintained).
- **Linux**: a tarball on GitHub Releases is the primary channel and works everywhere.
  Homebrew on Linux uses the same formula. AUR and Nix are cheap to add.
- **Windows**: WSL for v1. A native port means replacing `posix_spawn`, `mmap`, `pipe` and
  `poll` with `CreateProcess`, `CreateFileMapping`/`MapViewOfFile` and Win32 pipes. That's
  a real project, not a flag, which is why plan §10 lists it as a non-goal.

You noticed that installing a CLI tool usually drags in dependencies. That's the
shared-library model: a Homebrew formula declares `depends_on "openssl"` and brew installs
it as a separate package, so one copy is shared across tools. `pk` sidesteps this almost
entirely because it links nothing but the standard library. Fewer dependencies is a
distribution advantage, and it's worth *keeping* that property when you're tempted to add
a library later.

---

## 15. Why the index almost never needs rebuilding

The thing that makes this whole tool practical is that **git history is append-only**.

### Editing a file changes nothing

`pk` indexes **commits**, not your working tree. Saving a file, staging it, even
`git stash` — none of it is visible to `pk`, because none of it is visible to `git log -S`
either. `git log -S` has nothing to say about uncommitted work. So the "file changed →
reindex" reflex from search tools like `ctags` or an IDE's symbol index does not apply
here. Those index *a snapshot*, which changes constantly. This indexes *history*, which
only ever grows.

Concretely: the diff of commit `abc123` is a mathematical function of `abc123` and its
parent, both immutable. Its trigrams were computed once and are correct forever.

### So the only event that matters is a new commit

And new commits are handled without a rebuild at all. Plan §2.7: the header records which
ref tips were indexed, so a query can ask git for the difference:

```sh
git rev-list --all --not <indexed tips>     # usually empty, sometimes a handful
```

Those commits get handed to the verifier along with the index's candidates. Git checks them
directly. The answer is correct whether the index is an hour or a month old, because
anything the index doesn't know about is covered live.

That is the answer to "does running `pk` reindex implicitly": **no**, and it doesn't need
to. It closes the gap, which costs roughly one git diff per unindexed commit.

### So when does `pk update` actually run?

Automatically, and almost never. The reasoning is worth following because it's a caching
decision, and caching decisions have a shape you'll meet again.

Three options, and why two of them are wrong:

- **Make the user install a git hook.** Correct but unacceptable. The tool is supposed to be
  convenient, most people won't do it, and those who do may already have husky or
  `pre-commit` owning that hook file. Offer `pk hook install`; never require it, never
  install it silently.
- **Run `pk update` before every query.** Wrong for a subtler reason: updating costs *more*
  than covering the same commits live. Both have to run the same `git diff`; update
  additionally extracts trigrams, sorts, and writes a file. It also makes every query a
  write, which means a lock file, concurrency headaches, and disk churn for a command the
  user thinks is read-only.
- **Cover the gap live, and update only when the gap gets expensive.** This is the one. A
  small gap costs almost nothing because the commits ride along in the verification call
  that was already being spawned. A large gap is when the amortisation actually pays, so
  that's when you spend the write.

The threshold exists because the two costs cross over. Covering N commits live costs about N
git diffs *on every query*. Updating costs a bit more than N git diffs *once*. So below some
N it's cheaper to keep paying; above it, pay once. Start the threshold around a thousand and
tune it with real measurements.

What this means in practice: your own commits keep the gap in the single digits and never
trigger anything. The gap grows mainly when you `git pull` a batch of upstream work, and
then the next query absorbs an update and prints one line saying so. The user never learns
that `pk update` exists, which is the goal.

### The one case that *does* force a full rebuild

Operations that **rewrite** history rather than extend it: `git rebase`, `commit --amend`,
`filter-branch`/`filter-repo`, a force-pushed branch you then fetch, and `git gc` pruning
unreachable objects. These don't add commits, they replace them with different SHAs, which
invalidates the ordinal numbering. Detect it (the recorded tips are no longer reachable)
and rebuild. On a normal repo this happens rarely; on a repo where you rebase your own
feature branches constantly, those rewritten commits were mostly unreachable anyway.

### Why updates append a file instead of editing one

This is worth understanding because it's a general pattern, not a `pk` quirk.

Posting lists are stored **contiguously per trigram**, one after another, so a lookup is a
single seek plus a sequential read. That layout is why queries are fast. It is also why
*inserting* into it is miserable: adding one ordinal to the list for trigram `foo` means
every byte after `foo`'s list has to shift by one. Updating one commit rewrites the entire
multi-hundred-megabyte file.

The standard fix, used by Lucene, LevelDB, RocksDB, and most search engines, is a
**log-structured merge** arrangement:

- the big index is immutable, never edited;
- updates write a **new, small segment** file;
- a query runs against every segment and unions the results;
- occasionally a **compaction** merges segments back into one big one.

You trade a little query cost (a few segments to check instead of one) for making writes
cheap. `pk index` writes the base, `pk update` appends a segment, `pk compact` merges.
Recognising when a data structure wants this shape is a genuinely transferable skill.

### Where the space actually goes

Plan §4 has the sizing table. The intuition behind it:

- A commit's diff has on the order of 1500 *distinct* trigrams. The count is distinct-per-
  commit, not total, because a trigram appearing 50 times in one diff still produces one
  posting.
- Every (trigram, commit) pair is one posting. Postings are the whole cost; the trigram
  directory is a rounding error at 16.7M possible values, most of which never occur.
- A posting is an ordinal delta in a varint, so it costs a bit over one byte on average,
  not four.

Three levers control the size, in order of impact:

1. **Stopword culling.** Trigram frequency is Zipf-distributed: ` th`, `the`, `he ` appear
   in nearly every commit. They cost the most and filter the least. Dropping the top few
   percent removes a large share of all postings.
2. **The dense-commit cap.** A single commit importing a vendored library can contain more
   distinct trigrams than a thousand ordinary commits, while filtering nothing. Skip
   indexing those and mark them "always a candidate" so they're still verified.
3. **Delta + varint.** Already assumed above.

The number that surprises people is the *intermediate* size: before culling, the build
produces one 8-byte key per (trigram, commit) pair, which is ten to twenty times the final
index. That's a transient, and it's the entire reason the build is an external sort that
spills to disk rather than a big `std::vector` (plan §2.5).

### Is the size actually a problem?

Short answer: on disk it's real but fine, and in RAM it's a non-issue. Two things people
routinely get wrong here:

**A big mmap'd file is not big memory.** `mmap` maps the file into your address space
without reading it. Pages become resident only when touched, and they're clean pages backed
by the file, so the kernel can evict them under pressure without writing anything. A query
touches the header, a handful of directory pages during binary search, and a few posting
lists. Resident memory stays in the low megabytes whether the file is 90 MB or 1.2 GB. If
you had instead `read()` the whole index into a `std::vector`, you'd pay the full size in
RAM every run, which is exactly why the plan specifies mmap.

**The steady state isn't the risk; the build is.** A 1.2 GB index next to a packed repo of
several GB is ordinary derived data. It lives in `.git/`, it's never committed or pushed,
and deleting it costs a rebuild and nothing else. Treat it like a cache, because that's what
it is. The transient 15 GB of intermediate keys during a build is the thing that can
actually fail on a laptop, which is why the plan checks free space up front, culls before
spilling, and supports `--tmpdir`.

### How the size compares to things users already accept

The index lands at roughly **a quarter the size of the packed repo you already cloned**, and
it scales with history, so the people who see big numbers are the people the tool saves the
most time for. That is a healthy shape.

| repo | commits | index | repo on disk |
|---|---|---|---|
| a typical work repo | 5k | ~4 MB | tens of MB |
| `git.git` | ~80k | ~70 MB | ~250 MB |
| `llvm-project` | ~500k | ~450 MB | a few GB |
| `linux` | ~1.3M | ~1.2 GB | several GB |

For context on what developers already tolerate without complaint: `node_modules` is
routinely hundreds of MB **per project**, `ccache` defaults to a 5 GB cap, a JetBrains or
clangd index on a large C++ project runs to hundreds of MB or more, and a single Docker
image is often several GB. A derived index smaller than the IDE index for the same
codebase is not what stops adoption.

What *would* stop adoption is the first run: `pk index` takes minutes, and its transient
spill is ten to twenty times the final index. Failing at minute four with "no space left on
device" is a first impression you don't recover from. Check free space before starting,
show progress, and make the failure message say exactly how much is needed. That is a UX
problem, not a storage problem, and it's cheap to get right.

If someone genuinely can't spare the space, the stopword cull threshold is the tuning knob.
Culling more aggressively shrinks the index and lets more candidates through to
verification, trading disk for query time. That's a real dial, not a fudge, and it's worth
exposing once you've measured both ends of it.
