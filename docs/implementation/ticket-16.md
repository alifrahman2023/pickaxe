# Ticket #16 implementation evidence

Scope: [M1 / T01 — Build and install a minimal complete Git-backed search](https://github.com/alifrahman2023/pickaxe/issues/16),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Execution date: 2026-10-28. This is baseline implementation evidence, not
acceleration qualification or first-release acceptance.
The owner subsequently authorized #17 in the same PR; its evidence and current
handoff are in [ticket-17.md](ticket-17.md).

## Review baseline and local work

- Starting commit: `ab5aaff526cbda6ee55b174ab76ff10f2ff247d6`.
- Ticket branch: `ticket/16-git-backed-search`.
- Native `blocked_by` query returned `[]`; issue was open and unassigned before
  claiming it for the authenticated owner. No dependency was bypassed.
- Initial tracked tree contained no implementation. Existing untracked
  `.gitignore`, `AGENTS.md`, `CLAUDE.md`, `GLOSSARY.md`, and `docs/agents/*.md`
  were read, preserved, and excluded from ticket staging.
- Review command: `git diff ab5aaff526cbda6ee55b174ab76ff10f2ff247d6...HEAD`.
  A branch names a line of commits; this fixed SHA keeps the comparison stable
  even if `main` moves. Explicit path staging keeps unrelated local files out.

Read repository guidance/glossary, planning-map Notes, full specification,
ticket, and canonical
[compatibility](https://github.com/alifrahman2023/pickaxe/issues/2#issuecomment-6425250383),
[workflow](https://github.com/alifrahman2023/pickaxe/issues/3#issuecomment-6425795275),
[build](https://github.com/alifrahman2023/pickaxe/issues/14#issuecomment-6455044184), and
[implementation-plan](https://github.com/alifrahman2023/pickaxe/issues/7#issuecomment-6456274654)
resolutions. There were no applicable ADR files. The specification explicitly
approves the CLI-process testing seam used here; no new testing seam required
owner approval.

## Delivered behavior

`pk search <needle>` requires one nonempty literal needle. `pk search index`
searches for `index`; `pk index` is not implemented. One PATH lookup selects
Git, then a direct `execv` runs `--no-pager log --all -S<needle> --`.
Arguments own their bytes until the process replacement. Git inherits cwd,
environment, streams, and process identity, which directly preserves status
and signal termination. No shell construction, output buffering, index access,
or acceleration path is involved. README contains runnable build, installation,
and deterministic search demonstrations plus the C++/Git explanation.

## Actual environment

| Item | Observed identity |
| --- | --- |
| OS / architecture | macOS 15.7.4, build 24G517, arm64 |
| Kernel | Darwin 24.6.0, xnu-11417.140.69.708.3~1/RELEASE_ARM64_T8122 |
| Compiler | `/usr/bin/clang++`, Apple clang 17.0.0, clang-1700.0.13.5 |
| Compiler resolved by xcrun | `/Library/Developer/CommandLineTools/usr/bin/clang++` |
| Command Line Tools package | com.apple.pkg.CLTools_Executables 16.4.0.0.1.1747106510 |
| SDK | 15.5, `/Library/Developer/CommandLineTools/SDKs/MacOSX.sdk` |
| Standard library | bundled Apple libc++; `_LIBCPP_VERSION=190102`; linked libc++.1.dylib current version 1900.180.0 |
| C runtime | libSystem.B.dylib current version 1351.0.0 |
| CMake / generator | 4.1.2 / Unix Makefiles |
| Make | GNU Make 3.81, built for i386-apple-darwin11.3.0; successfully builds native arm64 output |
| PATH-selected Git | `/usr/bin/git`, 2.39.5 (Apple Git-154), runtime cpu arm64 |
| Git executable SHA-256 | `7f30f076d0e9c38f772a76449fca9da8cf97f6a3d43b94c90a00e4f9ce7ad39e` |
| Python (tests only) | 3.14.7 |
| Mounted data filesystem | `/dev/disk3s5`, APFS, local/journaled; no publication qualification implied |

No selected OS/compiler/Git mismatch was observed and no Git was substituted.
The CMake version exceeds the minimum. `diskutil info .` could not use the
DiskManagement framework in this session; `mount` independently reported the
local APFS data mount. This does not establish durability or mount qualification.

Build flags from `compile_commands.json`:
`-O3 -DNDEBUG -std=c++20 -Wall -Wextra -Wpedantic`.
Link flags: `-O3 -DNDEBUG -Wl,-search_paths_first -Wl,-headerpad_max_install_names`.
`file build/pk` reported a Mach-O 64-bit arm64 executable. `otool -L build/pk`
reported only the ordinary C++/C runtimes above. No checksum dependency is used
in this slice; vendoring/using XXH64 belongs to the later index-format work.
The tested executable SHA-256 was
`a6a5ca5fda5fc83abcef8a3c11835c762fb1d6edabb6140da125cd06ef73e8b3`.

## Actual checks

- Red/green tracer: the matching-history CLI test first failed because `pk`
  did not exist; after implementing the native CLI it passed against real Git.
- Configured Release with CMake/Unix Makefiles and `/usr/bin/clang++`, then ran
  `cmake --build build` regularly. All compilations/linking succeeded without
  warnings; C++20 is required with extensions disabled (`-std=c++20`).
  C++ compilation supplies type checking; there is no separate typechecker.
- Ran individual CLI tests during implementation. The explicit-color test
  initially failed because its custom reference format contained no colored
  field. Corrected the fixture to `%C(auto)%h%C(reset) %s`; it then passed
  without changing production code or overriding reference behavior.
- Final full implemented suite: `ctest --test-dir build --output-on-failure -V`
  passed **1/1 CTest entries, containing 10/10 Python checks**. It covers:
  complete addition/deletion matches and unchanged-count exclusion; successful
  empty zero-match output; a one-byte needle, literal `index`, leading hyphen
  and shell metacharacters; invalid operands; missing/unlaunchable Git; exact
  external Git status 37 with partial output; real Git failure outside a repo;
  config/environment/subdirectory preservation with explicit color; and
  deterministic basic SIGINT cancellation of a selected external executable.
- `cmake --install build --prefix <disposable-temp-prefix>` succeeded. The
  installed binary passed matching and zero-match CLI tests (2/2); the prefix
  was removed afterward. Direct build execution also passed the suite.
- Additional manual real-Git cancellation: created a disposable repository with
  `content diff=blocking`, configured `diff.blocking.textconv` to a Python helper
  that wrote a readiness/PID marker then blocked in `signal.pause()`. Launched
  `pk search needle` in a new process group; after helper readiness, sent group
  SIGINT. Git terminated with signal 2 (`subprocess` status `-2`), stdout was
  empty, and the helper PID no longer existed. No retry occurred. This is one
  basic scenario, not ticket #18's complete process-ownership evidence.
- Matching/config checks left `.git/pickaxe` absent. The implementation contains
  no index-resource operations.
- `git diff --check` passed. Final code-review results are recorded below.

## Code review

Applied the code-review skill with two independent parallel reviewers against
`ab5aaff526cbda6ee55b174ab76ff10f2ff247d6...7f25f5886358c11ecc4e89ade32837d182801f77`.
The commit was `7f25f58 Implement complete Git-backed search for #16`.
At the #16 handoff, only this evidence record changed after review. Subsequent
#17 test/documentation changes receive the review recorded in ticket-17.md.

### Standards

No findings. The diff follows the repository's documented guidance and glossary,
uses the approved CLI testing seam, and keeps unrelated local guidance outside
the commit. The small process-replacement implementation has no actionable
baseline smells. **0 documented violations, 0 smell findings.**

### Spec

Pass, **0 findings**. The baseline build/install, direct reference invocation,
one-time PATH lookup, argument ownership, inherited inputs, stdout/status,
diagnostics, and basic cancellation satisfy #16. No index operations or
acceleration were added. The reviewer independently reran the baseline CTest
entry and all 10 checks passed. Broader evidence remains assigned to #17/#18.

Standards: 0 findings; Spec: 0 findings; neither axis has an outstanding issue.
Final SHA-256 verification confirmed the preserved pre-existing local files were
unchanged; only the five explicit ticket paths are committed.

## Pending evidence and next ticket

The broader literal-byte/fallback/status catalogue was pending at the #16
handoff and is now delivered in [ticket #17](ticket-17.md); complete
real-Git/helper/terminal/process-ownership cancellation evidence was pending at
that handoff and is now delivered in [ticket #18](ticket-18.md).
Candidate/replay feasibility, indexing, checksum integration, memory and
publication audits, acceleration qualification, benchmarks, Linux preparation,
and two-platform release evidence remain pending in their assigned tickets.
Passing this baseline does not satisfy those obligations or enable acceleration.

The owner authorized combining #16/#17/#18 in PR #50, with the issues closing
when the PR is merged. Native dependency edges remain recorded. See
[ticket-18.md](ticket-18.md) for completed cancellation evidence and the current
handoff. Current next ticket is #19; it has not been started. The PR remains
unmerged for owner review.
