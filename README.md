# Pickaxe

`pk search <needle>` runs a complete literal Git history search. For example:

```sh
./build/pk search 'TODO'
./build/pk search 'index'
./build/pk search '-leading hyphen'
```

Supply exactly one nonempty needle; quote shell metacharacters, whitespace, or
newlines so your shell passes one argument. `index` is an ordinary needle after
`search`. `pk index` is reserved for later implementation and currently fails
with usage information. There are no search flags, path filters, or revision
operands.

Every valid search uses the Git executable found through the caller's inherited
PATH, resolved once. It directly executes the argument sequence equivalent to:

```sh
git --no-pager log --all "-S${needle}" --
```

Uppercase `-S` selects commits changing the occurrence count of the literal needle
within a file. It includes deletions and searches Git's complete current `--all`
scope. Git determines matches, order, formatting, and effective configuration.
Pickaxe adds one short fallback explanation on stderr and leaves stdout to Git.
It preserves Git's status, working directory, environment, and streams. A missing
Git returns 127; failure to launch the selected executable returns 126; invalid
input returns 2. Signal termination remains signal termination.

This first slice always uses Git fallback. Search creates no Pickaxe index
resources. Acceleration and indexing are not implemented or qualified.
Successful captured stdout is compared with the reference under stable inputs;
interactive pager/automatic terminal styling equivalence is outside the contract.

## Build and install on macOS

Prerequisites: Apple Clang 17 with bundled libc++ and macOS SDK (Xcode Command
Line Tools), CMake 3.28 or newer, Make, and installed Git on PATH. The selected
macOS target is 15.7.4 build 24G517, arm64, with PATH selecting `/usr/bin/git`
(Apple Git 2.39.5 / Apple Git-154). Building on another environment does not confer
acceleration qualification. Linux preparation belongs to milestone 9.

The development checks additionally require Python 3.8 or newer, using only its
standard library. Use `-DBUILD_TESTING=OFF` to build without Python.

```sh
command -v git
git --version
cmake -S . -B build -G "Unix Makefiles" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_CXX_COMPILER=/usr/bin/clang++ \
  -DCMAKE_INSTALL_PREFIX="$HOME/.local"
cmake --build build
ctest --test-dir build --output-on-failure
./build/pk search 'TODO'
cmake --install build
export PATH="$HOME/.local/bin:$PATH"
pk search 'TODO'
```

The build requires standard C++20 with extensions disabled. CMake generates Make
rules; compilation translates `src/main.cpp` into an object file, and linking
combines it with ordinary platform C++/C runtimes into one native `pk`. There are
no configure/build downloads or additional runtime dependencies. The later
index-format ticket owns the vendored checksum dependency.

Installation copies `pk` into `<prefix>/bin`. Rebuild and reinstall to upgrade.
Removing that executable does not remove repository index resources. For a
disposable installation smoke check, without touching your usual prefix:

```sh
prefix=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-install.XXXXXX")
cmake --install build --prefix "$prefix"
"$prefix/bin/pk" search 'TODO'
# Remove the temporary prefix when finished.
```

## Runnable demonstration and checks

This command constructs an isolated three-commit history, checks addition and
deletion matches against raw reference-Git stdout/status, and checks that a
commit preserving the occurrence count is excluded:

```sh
python3 tests/cli_baseline.py --pk ./build/pk \
  CliBaseline.test_complete_matching_search -v
```

Run the zero-match and argument demonstrations or the full baseline:

```sh
python3 tests/cli_baseline.py --pk ./build/pk \
  CliBaseline.test_zero_match_is_successful_empty_output \
  CliBaseline.test_short_and_metacharacter_arguments -v
ctest --test-dir build --output-on-failure
```

The approved testing seam is the CLI process with captured byte streams and
status against local Git. External executable fixtures control launch errors,
an exact failure status, and basic cancellation; they add no product options.
Fixtures isolate Git configuration for construction, and give Pickaxe and the
reference identical inputs, including the configuration/environment test.

`src/main.cpp` owns argument bytes in `std::string` objects. A null-terminated
pointer array borrows their storage until `execv`; strings are not mutated after
pointers are taken. Combining `-S` and the needle into one argument preserves
leading hyphens and arbitrary representable bytes without shell evaluation.
`execv` replaces Pickaxe with Git using the same process ID. No Pickaxe parent
waits for a child or translates its output/status; Ctrl-C reaches that process
as Git. More detailed real-Git/helper/process-group evidence remains ticket #18.

Ticket [#16](https://github.com/alifrahman2023/pickaxe/issues/16) evidence,
review baseline, limitations, and continuation are in
[docs/implementation/ticket-16.md](docs/implementation/ticket-16.md).
