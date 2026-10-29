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

The extended baseline checks 14 literal byte cases (including composed and
decomposed Unicode and invalid UTF-8), occurrence-count changes, binary blobs
containing NUL, configured bare-repository fallback, and real Git failure after
output. Run those demonstrations directly:

```sh
python3 tests/cli_baseline.py --pk ./build/pk \
  --evidence-dir ./build/evidence/demo \
  CliBaseline.test_literal_argument_bytes \
  CliBaseline.test_occurrence_counts_instead_of_matching_lines \
  CliBaseline.test_bare_repository_complete_fallback_leaves_resources_untouched \
  CliBaseline.test_real_git_failure_after_output_is_unsuccessful -v
```

CMake's CTest entry retains hexadecimal argument/stdout/stderr bytes, status,
fixture-source/executable hashes, configuration, and refs in
`build/evidence/cli-baseline/*.json`. Hex encoding is lossless; output is compared
as raw bytes before encoding. Temporary repositories are recreated on each run.
The evidence represents the tests run, not a qualification of acceleration.

A byte string need not be valid Unicode. C++ `std::string` owns bytes, while a
Unicode string represents characters; this CLI does not decode, normalize, or
case-fold the needle. A NUL byte ends a native CLI argument, so NUL is tested
inside blob contents instead. The selected Git still interprets its arguments
according to its effective configuration. On this macOS Git, the fixture's
`core.precomposeunicode=true` affects decomposed needles. The oracle retains
that setting; an external executable also verifies the exact forwarded bytes.

Moving or editing a line while keeping a needle's count unchanged need not
select the commit with `-S`. The count demonstration contrasts that result with
Git's line-based `-G` search. This is a test demonstration, not a product mode.
Bare repositories and custom output work through complete Git fallback; support
does not imply acceleration qualification.

`src/main.cpp` owns argument bytes in `std::string` objects. A null-terminated
pointer array borrows their storage until `execv`; strings are not mutated after
pointers are taken. Combining `-S` and the needle into one argument preserves
leading hyphens and arbitrary representable bytes without shell evaluation.
`execv` replaces Pickaxe with Git using the same process ID. No Pickaxe parent
waits for a child or translates its output/status; Ctrl-C reaches that process
as Git. The following checks establish real-Git/helper/process-group evidence.

Cancellation is checked before and after observable stdout against real Git,
using both foreground-process-group SIGINT and actual Ctrl-C on a controlled
terminal. Readiness comes from a local socket handshake; checks wait for stream
EOF/status and verify the process group is empty. No sleeps decide when to
cancel. Tests create their own sessions and terminals, so they do not signal
your existing shell or jobs:

```sh
python3 tests/cli_baseline.py --pk ./build/pk \
  --evidence-dir ./build/evidence/cancellation \
  CliBaseline.test_real_git_cancellation_before_and_after_stdout \
  CliBaseline.test_streams_and_inherited_descriptor_ownership -v
```

These macOS checks require local access to PTYs and process-group inspection.
The terminal delivers Ctrl-C to its foreground group, including Git's converter;
sending a signal only to a single PID is a different operation. A cancelled
search is unsuccessful even if it already wrote bytes. Those bytes are an
incomplete result, not a successful empty or complete search.

Resource lifetime matters at both boundaries. On launch failure, C++ objects
release owned memory when their scopes unwind normally (RAII). On successful
`execv`, the kernel replaces the old process image; C++ destructors do not run.
Pickaxe owns no helper pipes or descriptors in this baseline: Git receives the
caller's streams and intentionally inherited descriptors. Tests check binary
stdin/stdout, stream EOF, success/failure statuses, and absence of additional
descriptors. Context managers close test sockets, pipes, and PTYs; failure
cleanup targets only the new test process group.

Input validation and byte ownership are ordinary C++20; PATH lookup and
`execv` form the small POSIX process boundary. PTY/`ps`/`/dev/fd` checks are
macOS evidence. Future subprocess helpers and Linux adaptation need their own
ownership checks; no general subprocess framework has been introduced.

Ticket [#16](https://github.com/alifrahman2023/pickaxe/issues/16) evidence,
review baseline, limitations, and continuation are in
[docs/implementation/ticket-16.md](docs/implementation/ticket-16.md).
The follow-on [ticket #17 evidence](docs/implementation/ticket-17.md) records
the extended checks and retained raw comparison bundle in the same PR.
[Ticket #18 evidence](docs/implementation/ticket-18.md) records the completed
cancellation/descriptor checks, current handoff, and raw process traces.

The development-only [ticket #19 containment model](docs/implementation/ticket-19.md)
checks complete blob associations against independent tree snapshots and matches
against Git. Run it without building or enabling an accelerator:

```sh
python3 tests/candidate_containment.py --evidence-dir build/evidence/candidate-containment -v
```

Its trace includes actual candidates, reference matches, coverage, associations,
and conservative bypasses. The Python model intentionally loads tiny fixtures
into memory; it is not the bounded C++ index builder. The same evidence note
includes runnable Git object and C++ byte-string demonstrations.

The [ticket #20 replay gate](docs/implementation/ticket-20.md) adds one ordered
`--no-walk=unsorted --stdin` Git verification session and a guarded empty path in
the same development-only suite. Eleven containment/replay checks retain exact
stdout/status and scope/candidate evidence. Run the focused gate examples:

```sh
python3 tests/candidate_containment.py \
  Containment.test_replay_prunes_and_preserves_one_formatting_session \
  Containment.test_replay_empty_guard_and_unborn_outcome -v
```

Passing these tiny fixtures establishes feasibility on this tested environment;
it enables no product acceleration. Eligibility implementation, publication
investigations, production indexing and full qualification remain pending.


The [initial dependency inventory](docs/implementation/eligibility-inventory.md)
and [ticket #21 experiments](docs/implementation/ticket-21.md) identify effective
config/attribute sources and conservative eligibility limits. Five development
checks exercise scopes/includes/environment, attribute text conversion, custom
output, rename/submodule settings, and incomplete inspection. No eligibility
parser or product acceleration is enabled:

```sh
python3 tests/candidate_containment.py \
  Containment.test_dependencies_config_sources_and_environment_precedence \
  Containment.test_dependencies_attribute_sources_and_text_conversion \
  Containment.test_dependencies_output_profiles_against_early_replay -v
```

For the shared macOS CI/local build-and-check command, validated evidence
collection, and reliable GitHub CLI operations, see
[development checks](docs/development.md).

The development-only [benchmark workload preparation](docs/implementation/ticket-23.md)
retains fixed Git/Linux source histories and exact needle manifests. Large-history
preparation and measurements are separate from normal builds and tests. Previously
characterized snapshots can be validated through object-file hashes without
walking their histories again. Run the tiny tooling checks with:

```sh
python3 tests/check_evidence.py BenchmarkWorkloads -v
```
