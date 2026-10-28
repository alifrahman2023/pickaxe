# Initial eligibility dependency inventory (#21)

This is a proposed observation/classification inventory for the narrow profile
in [specification R11](https://github.com/alifrahman2023/pickaxe/issues/15) and
[canonical qualification](https://github.com/alifrahman2023/pickaxe/issues/8#issuecomment-6454602425).
It is **not an implemented eligibility parser or a qualified profile**. The live
experiments and execution results belong to the accompanying #21 evidence note.
Production `pk` continues whole-search Git fallback.

**A** means a proposed accepted condition *after its exact profile qualifies*;
**R** means whole-search fallback in the initial profile; **D** means inspection
or proof remains deferred, so acceleration must not accept it yet. These are
Pickaxe decisions/inferences, distinct from the Git facts cited below. Nothing
here expands the agreed profile or treats all settings under one prefix alike.

## Inputs and proposed observations

| Input | Concrete observation | Initial decision and recheck obligation |
| --- | --- | --- |
| Selected Git | Resolve inherited `PATH` once; retain executable path, resolved file identity/hash, `git version --build-options`, `git --exec-path`, OS/runtime identity and applicable helper/build identities. | **A:** exact tested artifact/environment only; **R:** unknown build/wrapper. A matching version string is insufficient. Recheck artifact inputs used by the proof; a pathname/hash observation does not pin an executable against every race. This follows the [build resolution](https://github.com/alifrahman2023/pickaxe/issues/14#issuecomment-6455044184). |
| Config sources | `git --no-pager config --includes --null --show-origin --show-scope --list`, under the same cwd/environment as the reference; retain ordered duplicate values and typed interpretation where relevant. | **A:** understood values from fully resolved system, XDG/global, local, optional worktree and command scopes. **R:** malformed/unreadable required input, incomplete origin inspection or potentially relevant unknown value. Scope/origin output identifies consulted values, not a complete filesystem dependency manifest. [Git config](https://github.com/git/git/blob/v2.39.5/Documentation/git-config.txt) |
| Includes | Inspect `include.path` and `includeIf.*.path` edges, target presence/readability/content, and predicates depending on Git-directory spelling, branch and remote URLs. | **D:** complete include graph/dependency capture and recheck in #34. Missing/inactive targets need explicit treatment; a later file creation or predicate change may alter effective values. **R:** unresolved edges or unknown conditions. Remote URLs can influence `hasconfig:remote.*.url` even though they do not directly select search matches. [Include rules](https://github.com/git/git/blob/v2.39.5/Documentation/config.txt) |
| Config environment | Inspect `HOME`, `XDG_CONFIG_HOME`, `GIT_CONFIG_SYSTEM/GLOBAL/NOSYSTEM`, `GIT_CONFIG_COUNT/KEY_n/VALUE_n`, and inherited `GIT_CONFIG_PARAMETERS`; keep command-scope values in the manifest. | **D:** robust provenance/precedence handling. `GIT_CONFIG` affects the config command alone, so an inherited value can misdirect an observer while leaving `log` unchanged. Do not mistake that observation for log's effective configuration. Unexpected override mechanisms require fallback until handled. [Git config environment](https://github.com/git/git/blob/v2.39.5/Documentation/git-config.txt), [parameter decoding](https://github.com/git/git/blob/v2.39.5/config.c) |
| Current scope | Ask selected Git for full `rev-list --all`; observe refs with `for-each-ref` including full IDs/symbolic targets, plus symbolic/detached/unborn HEAD state. | **A:** ordinary branches/tags/detached HEAD, covered and uncovered commits; their presence alone is not fallback. Capture/recheck actual current refs/HEAD dependencies, not equality with build-time refs. Preserve Git's traversal order. [Traversal options](https://github.com/git/git/blob/v2.39.5/Documentation/rev-list-options.txt) |
| Repository interpretation | `rev-parse --absolute-git-dir`, `--path-format=absolute --git-common-dir`, `--is-bare-repository`, `--is-inside-work-tree`, `--show-object-format`, `--is-shallow-repository`; inspect format/extensions, common-directory identity, alternates, grafts/replacements and promisor/partial state. | **A:** ordinary complete SHA-1 working tree only. **R:** bare/linked-worktree/shallow/partial/alternate layouts, replacements/grafts, unsupported format/extensions or unresolved interpretation. Successful discovery alone proves none of these absent. [Layout](https://github.com/git/git/blob/v2.39.5/Documentation/gitrepository-layout.txt), [format rules](https://github.com/git/git/blob/v2.39.5/Documentation/technical/repository-version.txt), [rev-parse](https://github.com/git/git/blob/v2.39.5/Documentation/git-rev-parse.txt) |
| Object access | Resolve Git's actual object locations, alternates and relevant environment; require every necessary enumeration/object read to succeed. | **R:** missing/unreadable objects or incomplete helpers; never interpret absence of readable data as a nonmatch. Repacking does not change object identities, but reads can still fail. [Repository layout](https://github.com/git/git/blob/v2.39.5/Documentation/gitrepository-layout.txt) |
| Attribute sources | Inspect repository root/nested `.gitattributes`, index fallback, `$GIT_DIR/info/attributes`, `core.attributesFile`/XDG-HOME default and system attributes; query `check-attr -z --stdin diff` for relevant paths. | **D:** complete source/path coverage and rechecks in #34. `check-attr` reports values, not origins; `--cached` changes which repository attribute source is consulted. Query old/deleted/renamed historical paths too: enumerating only current tracked files is insufficient. Do not assume historical blobs automatically supply historical attributes to `log`. **R:** inability to rule out an applicable converter. [Attribute precedence](https://github.com/git/git/blob/v2.39.5/Documentation/gitattributes.txt), [check-attr](https://github.com/git/git/blob/v2.39.5/Documentation/git-check-attr.txt) |

An observer must preserve reference inputs. Internal extraction's explicit
`--no-relative --no-renames --no-ext-diff --no-textconv
--ignore-submodules=none` protects enumeration; it is not permission to apply
those settings to the reference search. This separation comes from the
[architecture resolution](https://github.com/alifrahman2023/pickaxe/issues/6#issuecomment-6428299180).

## Representative setting classifications

| Setting/effect | Initial classification |
| --- | --- |
| `core.repositoryFormatVersion`, `core.bare`, `core.worktree`, `extensions.*`: repository interpretation. | **A:** understood ordinary target values; **R:** unsupported interpretation/extension; **D:** complete extension/value inventory. [Repository format](https://github.com/git/git/blob/v2.39.5/Documentation/technical/repository-version.txt) |
| `core.precomposeUnicode`, `core.ignoreCase`, attribute-related core settings: path/byte interpretation. | **D:** retain actual macOS defaults and prove their effects; do not normalize needles or assume all non-ASCII profiles equivalent. `core.fileMode`, `core.autocrlf`, `core.eol` describe worktree/index operations rather than rewriting existing blob identities; any irrelevance classification must also account for the attribute/read path actually used. [Core settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/core.txt) |
| `diff.renames`, `diff.renameLimit`, `diff.relative`: pairing/enumeration/reference diff behavior. | **A:** qualified defaults only; **R/D:** nondefault values pending explicit proof. Complete old/new enumeration survives internal rename disabling, but that does not establish every reference setting's semantics. [Diff settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/diff.txt) |
| `diff.ignoreSubmodules`, `submodule.*.ignore`, `diff.submodule`: submodule comparison/presentation. | **R/D:** nondefault behavior until classified/tested. Gitlink-changing commits always remain candidates; do not infer settings are irrelevant because a helper ignores them. Default gitlinks themselves are required supported cases. [Diff settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/diff.txt), [submodule config](https://github.com/git/git/blob/v2.39.5/Documentation/config/submodule.txt) |
| `diff.<driver>.textconv`, `.cachetextconv`, `.binary`, `.command`; `diff.external`; `diff` attributes: content interpretation/helper behavior. | **R:** applicable text conversion or inability to exclude it; **D:** other driver/external-diff relevance. Count-based pickaxe can operate on converted content, so a raw-blob filter cannot establish containment there. Preserve the user's setting through fallback. [Pickaxe implementation](https://github.com/git/git/blob/v2.39.5/diffcore-pickaxe.c), [drivers](https://github.com/git/git/blob/v2.39.5/Documentation/gitattributes.txt) |
| `log.showRoot`, `log.diffMerges`, `log.follow`: selection/diff behavior. | **A:** qualified defaults only; **D/R:** nondefaults until their actual effect for this exact argument sequence is established. Retaining merges does not waive replay equivalence. [Log settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/log.txt) |
| `format.pretty`, `pretty.*`, custom `%S`: formatting and revision-source dependence. | **R:** custom output in the initial profile. `%S` can reveal reference names in the reference but supplied object IDs in replay; do not rewrite the reference format. A `format.*` option used only by format-patch can eventually be classified irrelevant instead of rejecting its entire prefix. [Pretty formats](https://github.com/git/git/blob/v2.39.5/Documentation/pretty-formats.txt), [log configuration consumer](https://github.com/git/git/blob/v2.39.5/builtin/log.c) |
| `color.*`, `log.decorate`, `log.date`, `log.abbrevCommit`: captured output bytes. | **A:** qualified default nonterminal behavior; **R:** explicit colors/decorations or nondefault date/output profiles. `--no-pager` does not disable explicit color. [Log settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/log.txt), [Git options](https://github.com/git/git/blob/v2.39.5/Documentation/git.txt) |
| `notes.*`, `core.notesRef`, `log.showSignature`, `gpg.*`, `log.mailmap`, `mailmap.*`, `.mailmap`: output and external inputs. | **R:** notes/signature display or unqualified mailmap behavior; **D:** complete default mailmap/source audit. Capture content/file dependencies, not only config keys. [Log options](https://github.com/git/git/blob/v2.39.5/Documentation/git-log.txt), [log consumer](https://github.com/git/git/blob/v2.39.5/builtin/log.c) |
| `i18n.commitEncoding`, `i18n.logOutputEncoding`: decoding/re-encoding. | **A:** recorded qualified encoding only; **R:** nondefault/unqualified output encoding. A UTF-8 locale alone does not establish the effective setting or stored commit encoding. [Encoding configuration consumer](https://github.com/git/git/blob/v2.39.5/config.c) |
| `remote.<name>.url`: transport endpoint. | **A as irrelevant to local search only after include predicates are resolved** in the accepted complete repository. Do not generalize to promisor fetches or `includeIf.hasconfig`. [Remote settings](https://github.com/git/git/blob/v2.39.5/Documentation/config/remote.txt), [conditional includes](https://github.com/git/git/blob/v2.39.5/Documentation/config.txt) |
| Unknown potentially relevant keys/values or unreadable origins/attributes. | **R:** whole-search fallback; Git accepting a key does not classify it for Pickaxe. Document each accepted irrelevance exception by effect. No opaque configuration fingerprint substitutes for this reasoning. [Canonical rule](https://github.com/alifrahman2023/pickaxe/issues/8#issuecomment-6454602425) |

## Environment classes and detection limits

The proposed gate must inspect these classes rather than silently clearing them:

- **Discovery/configuration:** `PATH`, `GIT_EXEC_PATH`, cwd, `HOME`,
  `XDG_CONFIG_HOME`, config variables above, `GIT_DIR`, `GIT_COMMON_DIR`,
  `GIT_WORK_TREE`, `GIT_CEILING_DIRECTORIES`, `GIT_DISCOVERY_ACROSS_FILESYSTEM`.
- **Object/scope interpretation:** `GIT_OBJECT_DIRECTORY`,
  `GIT_ALTERNATE_OBJECT_DIRECTORIES`, `GIT_NAMESPACE`, `GIT_REPLACE_REF_BASE`,
  `GIT_NO_REPLACE_OBJECTS`, `GIT_GRAFT_FILE`, `GIT_SHALLOW_FILE`, and unknown
  `GIT_*` inputs potentially affecting interpretation.
- **Content/attributes/helpers:** `GIT_INDEX_FILE`, `GIT_ATTR_NOSYSTEM`,
  `GIT_EXTERNAL_DIFF`, `GIT_DIFF_OPTS`, pathspec environment switches, and
  converter executable/runtime/environment when relevant. Initial fallback avoids promising converter reproducibility.
- **Output:** `LC_ALL`, `LC_CTYPE`, `LANG`, `LANGUAGE`, `TZ`, encoding settings,
  `GIT_NOTES_REF`, `GIT_NOTES_DISPLAY_REF`; terminal/pager-related state as relevant
  to the fixed nonterminal, `--no-pager` contract. `GIT_PAGER` does not justify
  changing that reference contract.

These are an initial effect-based audit list, not an exhaustive parser allowlist.
Discovery/object variables are documented in
[Git's environment](https://github.com/git/git/blob/v2.39.5/Documentation/git.txt)
and [environment-name definitions](https://github.com/git/git/blob/v2.39.5/cache.h);
attribute-system switching is implemented in
[`attr.c`](https://github.com/git/git/blob/v2.39.5/attr.c).
Unknown or uninspectable potentially relevant inputs remain **R**.

Capture then recheck the actual dependency manifest before accelerated stdout:
Git identity, repository interpretation, current refs/HEADs, resolved config
sources/includes and relevant environment, and attribute/mailmap sources needed
by the accepted proof. Presence/absence is an input too. Git may ignore some
missing/unreadable system/global sources, so a successful config query does not
prove exhaustive inspection. Relevant warnings/errors require investigation or
fallback. Source-by-source metadata/content checks can detect changes, but no
separate discovery calls provide an atomic repository snapshot; change-and-revert,
permissions and external inputs limit detection. These are conservative checks
under [R03/R11](https://github.com/alifrahman2023/pickaxe/issues/15).

## Selected Apple Git probe observations

Local probes using `/usr/bin/git` (Apple Git 2.39.5 / Git-154) found that an
exact `includeIf.gitdir` condition matched the absolute Git directory reported
by Git **without a trailing slash**. Appending `/` did not match that directory;
Git documents a trailing-slash pattern as matching beneath it. In this discovered
fixture, the `/private/var/.../.git` spelling matched while the `/var/.../.git`
alias did not. Preserve the actual discovery/predicate inputs rather than
assuming every path spelling interchangeable. [Pattern rules](https://github.com/git/git/blob/v2.39.5/Documentation/config.txt)

With `GIT_CONFIG_NOSYSTEM` absent and `GIT_CONFIG_SYSTEM=/dev/null`, combined
configuration inspection still reported
`/Library/Developer/CommandLineTools/usr/share/git-core/gitconfig` with scope
`unknown`. Explicit `--system` inspection did not report it; setting
`GIT_CONFIG_NOSYSTEM=1` suppressed it in the probe. An unknown **scope label** is
not an unknown **key**: retain its origin, inspect its contents/dependencies and
classify each effect. Do not discard vendor origins or broadly accept them.
This is selected-artifact evidence, not an inferred upstream guarantee.
[Ticket #21's execution note](ticket-21.md) retains the path-pattern and vendor
scope/environment matrices and their limitations.

## Deferred acceptance work

[#34](https://github.com/alifrahman2023/pickaxe/issues/34) still owns the real
conservative gate: complete parsing/normalization and multivalue semantics,
source/include/attribute manifests, unknown-input decisions, repository-layout
checks, capture/recheck, and one complete fallback with unchanged reference
configuration. If inspection cannot credibly exclude a dependency, reject that
case rather than adding a blanket fingerprint or weakening containment.

[Qualification Q.C](https://github.com/alifrahman2023/pickaxe/issues/8#issuecomment-6454602425)
still requires actual gate rejection and exact forwarded output/status for every
excluded layout/profile and representative config/environment/attribute source,
including includes, environment overrides, text conversion, `%S`, colors,
decorations, date/encoding changes, notes/signatures and unreadable/unknown inputs.
Source review or a passing probe is not that gate evidence. Wider Q.A–G and
platform qualification remain separately required.

Git documentation/source links above target primary upstream Git v2.39.5 files.
They guide inspection but do not establish that Apple Git-154 has identical
behavior; the selected executable's recorded experiments supply local evidence.
