# Ticket #21 effective-dependency investigation

Scope: [#21 — M2 / T06 — Investigate effective dependencies for eligibility](https://github.com/alifrahman2023/pickaxe/issues/21),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Executed 2026-10-28 on the existing macOS target. The
[initial eligibility inventory](eligibility-inventory.md) is the source-backed
accepted/rejected/deferred classification and observation proposal.

**Result:** representative inputs can be observed, and concrete inspection traps
and conservative fallback rules are recorded. No fundamental inability to
inspect the narrow profile was established. Complete dependency discovery and
the final eligibility parser remain unfinished work for #34 and Q.C; the product
still runs complete Git fallback. This investigation qualifies no acceleration.

## Baseline and scope

- Continued `ticket/19-candidate-containment` / draft PR #51 on the owner's
  instruction to add the next ticket if it fit. This investigation directly
  examines the assumptions behind #19/#20, so it belongs with that evidence.
- #21 starts at `ec8c0d875c7639d44bd8765efb51b479b7635efc`. Combined PR baseline
  stays `b76a046b383afb3b7fc7652813fdc87e1d9268ec` (merged milestone-1 PR #50).
- Native #20 blocker remains open, with its passing gate/evidence/reviews already
  complete before this owner-authorized continuation. No issue was closed or
  dependency removed. #21 was open/unassigned and claimed for the owner.
- Read #21, #15, map #1 Notes, repository guidance/glossary, canonical compatibility,
  architecture, qualification, build and implementation-plan resolutions. The
  refreshed specification/map are unchanged. No applicable ADR exists.
- Used the implement, TDD and research skills. The research skill's background
  agent produced the primary-source inventory and narrowly investigated Git
  observations. Experiments use the already approved candidate/path and
  command-byte/status observation seams, with no product option or final gate.
- Preserved all seven original untracked local files, excluded from commits.
  No production C++, installation, index resource, Linux preparation, planning
  map or resolved-decision changes.

## Concrete inventory and proposed decisions

The inventory enumerates Git executable/build/helper identity; all configuration
scopes, includes/predicates and environment overrides; current refs/HEADs;
repository layouts/formats/extensions and object access; attribute sources and
historical pathname coverage; and discovery/content/output/locale/timezone
inputs. It classifies representative `core`, `extensions`, `diff`, `submodule`,
`log`, `format`, `pretty`, `color`, `notes`, `i18n`, mailmap/signature and transport
settings by their effect, with source citations.

Its **A** entries are proposed accepted conditions only after their exact narrow
profile qualifies. **R** requires whole-search fallback in the initial profile.
**D** is unfinished inspection/proof, so acceleration cannot accept it yet.
No generic config fingerprint replaces source provenance, include predicates,
attribute applicability, unknown-key classification or capture/recheck of the
actual dependencies. Git's acceptance of an option is not Pickaxe qualification.

## Five new live checks

`tests/candidate_containment.py` extends the existing fixture suite; model and
replay implementations remain unchanged. Each command now records its own
selected environment, because teardown's final environment cannot explain earlier
calls after an override changes. The first observation test failed with missing
per-call environment, then passed after adding that evidence field (version 3).

1. **Configuration sources and precedence.** Controlled system/global sources,
   unconditional and active `gitdir` includes, local config, worktree config,
   `GIT_CONFIG_COUNT/KEY_0/VALUE_0`, and `-c` are observed with origin/scope/NUL
   framing. Effective date values progress through included `raw`, local
   `iso-strict`, worktree `unix`, environment `relative`, and command `short`.
   Adding a remote URL activates a `hasconfig:remote.*.url` include. Thus a remote
   URL is harmless to local search only after include effects are resolved.
2. **Attribute sources and raw content.** A controlled global attribute file,
   working-tree `.gitattributes`, and `.git/info/attributes` successively select
   different named drivers, as independently reported by `check-attr`. Applicable
   text conversion makes `converted-only` match historical raw bytes that do not
   contain it. The frozen raw model yields no candidates, so its empty replay
   differs from the unchanged reference. This is an expected rejected-profile
   observation, not a default-profile containment failure or eligibility pass.
3. **Output settings against the early replay.** `format.pretty=format:%S:%H`
   changes revision-source information: reference names differ from replay's
   supplied IDs. Exact output differs, as expected for a rejected custom profile.
   Explicit color, full decoration, ISO dates and ISO-8859-1 log encoding each
   change reference bytes too; `café` is re-encoded in the encoding case. The
   probe retains whether replay happens to agree, without accepting any of those
   unqualified profiles. Reference config is never overridden to obtain equality.
4. **Rename/submodule effects.** `diff.renames=true` excludes a pure rename from
   `-Sneedle`; `false` selects it. `diff.ignoreSubmodules=none` selects the gitlink
   addition for `Subproject commit <full-ID>`; `all` suppresses it. Complete
   associations/gitlink bypass retain every match and replay still agrees in
   these small cases. This is effect evidence, not qualification of nondefaults.
5. **Unknown/incomplete/observer inputs.** Git accepts an unknown potentially
   relevant `diff` key. An absent include target still yields a successful config
   listing, so success alone does not establish complete inspection. Malformed
   include syntax and a directory used as a config file produce diagnostics/failure.
   Proposed gates reject unknown potentially relevant input or incomplete source
   inspection. Finally, `GIT_CONFIG` redirects the config observer to an `iso`
   date setting while `log` still uses actual local `short` dates: the observer
   must distinguish this variable from actual search configuration overrides.

These are observations with explicit proposed decisions, not a detector whose
fallback paths have been qualified. The original independent association/match
oracles and exact default-profile replay checks remain in the full suite.

## Additional selected-Git findings and limits

A failing initial include fixture used the exact Git-directory path with a
trailing slash. A minimized matrix found exact canonical `.git` without `/`
matched; `.git/` instead describes paths underneath and did not match the
directory itself. A `/var` alias also differed from the `/private/var` spelling
in this probe. Corrected the fixture's intended active condition; preserved the
initial record and eight-case matrix. No candidate/replay oracle was weakened.

With `GIT_CONFIG_NOSYSTEM` absent, overriding `GIT_CONFIG_SYSTEM=/dev/null` still
left an Apple vendor origin at scope `unknown` in combined inspection:
`/Library/Developer/CommandLineTools/usr/share/git-core/gitconfig`. Explicit
`--system` inspection alone did not show it. `GIT_CONFIG_NOSYSTEM=1` suppressed
it in the twelve-case matrix. Unknown scope labels must not make a parser drop
origins or confuse known keys with unknown potentially relevant values. This
shows why an upstream version string and a single source query are insufficient;
it does not assert Apple Git is identical to upstream v2.39.5.

The proposed observer can conservatively reject incomplete/unknown cases, but
these limits remain explicit:

- Effective config values alone omit absent/inactive include dependencies; paths,
  predicate inputs, existence, read errors and later creation matter.
- `check-attr` provides effective values without provenance. System/default,
  nested/index fallback and old/deleted/renamed pathname sources need a complete
  manifest. Converter applicability cannot be ruled out by checking only current
  files. The live test covers representative sources, not every attribute class.
- Discovery, environment, refs/HEADs, object interpretation, attributes, mailmaps
  and executable inputs require coordinated capture/recheck. Separate calls do
  not form an atomic snapshot or detect every change-and-revert race.
- Unknown origins, keys, values or relevant environment and unreadable dependencies
  require whole-search fallback before accelerated stdout. Failure after stdout
  remains nonzero without replacement output; cancellation never retries.

No broad claim that arbitrary configuration can always be inspected is made.
If #34 cannot credibly implement an inspection, that profile must remain rejected
and the affected assumption must be surfaced before dependent acceleration.

## Actual checks and retained evidence

- C++20 Release build passed. Focused new checks passed during development.
- Full suite: **2/2 CTest entries, 34/34 Python checks, no skips**: 18 unchanged
  CLI checks plus 16 containment/replay/dependency checks. All previous cases
  rerun under the canonical full-rerun policy. macOS PTY/process checks ran with
  required local access. Recorded duration: 20.40 seconds; no performance claim.
- A live C++ CLI demonstration below uses environment-injected custom `%S`
  formatting. `pk` retains the same successful stdout bytes as reference Git
  through whole-search fallback. No install behavior changed.
- Selected Git remains `/usr/bin/git`, Apple Git 2.39.5 (Apple Git-154), on macOS
  15.7.4 / 24G517, arm64. Compiler remains Apple Clang 17; CMake 4.1.2. Git build
  options, exec path, binary/source hashes and host/tool observations are retained.
- [evidence/ticket-21.json.gz](evidence/ticket-21.json.gz) retains all 34 records,
  raw argument/environment/stdin/stdout/stderr/status observations, source/Git/
  binary hashes, refs/config/attribute results, candidate and profile traces,
  full CTest log, the initial red/include observations, minimized include/vendor
  matrices, identity capture and CLI demonstration. Hex/gzip encode storage,
  not oracle comparisons. Round trip and current source hashes were verified.
  Earlier archives remain historical source-pinned evidence.

## Runnable demonstrations and C++ concept

```sh
cmake --build build
python3 tests/candidate_containment.py --evidence-dir build/evidence/candidate-containment \
  Containment.test_dependencies_config_sources_and_environment_precedence \
  Containment.test_dependencies_attribute_sources_and_text_conversion \
  Containment.test_dependencies_output_profiles_against_early_replay \
  Containment.test_dependencies_rename_and_submodule_settings \
  Containment.test_dependencies_unknown_missing_invalid_and_observer_inputs -v
ctest --test-dir build --output-on-failure -V
```

Inspect representative decisions and actual evidence paths:

```sh
python3 - <<'PY'
import json
from pathlib import Path
for p in sorted(Path('build/evidence/candidate-containment').glob('test_dependencies_*.json')):
    print(p.name)
    for t in json.loads(p.read_text())['traces']:
        print(t['path'], t.get('classification'),
              'containment:', t.get('containment'), 'same bytes:', t.get('stdout_equal'))
PY
```

C++'s owned `std::string` arguments preserve bytes, but `argv` alone does not
specify Git behavior. `execv` also retains cwd and inherited environment. The
existing C++ CLI resolves `PATH` with `std::getenv`, then executes Git without
clearing its configuration inputs. It therefore supports the following custom
profile through fallback even though the early replay cannot qualify `%S`:

```sh
demo=$(mktemp -d "${TMPDIR:-/tmp}/pickaxe-config.XXXXXX")
env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=format.pretty \
  GIT_CONFIG_VALUE_0='format:%S:%H' \
  ./build/pk search 'std::string' > "$demo/pk"
env GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=format.pretty \
  GIT_CONFIG_VALUE_0='format:%S:%H' \
  git --no-pager log --all '-Sstd::string' -- > "$demo/git"
cmp "$demo/pk" "$demo/git"
```

The demo changes only those child-process environments; it writes no repository
configuration. Effective config is the layered result plus applicable includes
and environment. Attributes independently select per-path interpretation.

## Review and handoff

Applied the code-review skill with independent parallel reviewers against
`ec8c0d875c7639d44bd8765efb51b479b7635efc...399a8f0` (one implementation commit).

### Standards

Pass: **0 documented violations, 0 actionable smell findings**. The reviewer
independently reran all five dependency probes and verified the archive's source
hashes, 34 records and whitespace check.

### Spec

Pass: **0 findings**. The reviewer independently reran all five probes and
verified the inventory's required classes, unchanged reference settings,
Apple-specific limitations, 34 records and 34/34 full-suite pass. The initial
conditional fixture correction did not weaken any containment/replay oracle.
Final parser/provenance work and actual rejection qualification remain #34/Q.C.

Standards: 0 findings; Spec: 0 findings; neither axis has an outstanding issue.
Only review/handoff documentation changed after review. `git diff --check` and
all seven preserved-local-file hashes passed. Only #19/#20/#21 belong to this
draft PR.
Stop before marking ready, merging, closing issues or starting another ticket.

Next ticket, **not started**:
[#22 — Investigate the macOS publication protocol](https://github.com/alifrahman2023/pickaxe/issues/22).
The real eligibility implementation remains #34; qualification Q.C must prove
actual rejection and exact complete fallback for excluded layouts/settings and
representative input sources. This report is not a substitute for those gates,
full qualification, bounded indexing, or two-platform release evidence.
