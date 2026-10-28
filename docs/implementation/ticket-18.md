# Ticket #18 implementation evidence

Scope: [M1 / T03 — Verify cancellation and Git process ownership](https://github.com/alifrahman2023/pickaxe/issues/18),
under [specification #15](https://github.com/alifrahman2023/pickaxe/issues/15).
Execution date: 2026-10-28. This completes milestone 1's Git-backed baseline;
it does not qualify acceleration or establish future indexing/helper behavior.

## Baseline, dependency, and sources

- Continued `ticket/16-git-backed-search` and PR #50 on the owner's explicit
  instruction to add the next ticket. #18 starts at
  `e2ce57bcd7446500dd697b8fa7f7e246e9b532fe`. The combined review baseline stays
  `ab5aaff526cbda6ee55b174ab76ff10f2ff247d6`.
- Native blockers report open #17. Its implementation/evidence/reviews passed
  before this slice; the owner authorized adding #18 atop it in the same PR.
  Native dependency edges remain intact. #18 was open/unassigned and claimed
  for the owner. #16/#17/#18 close on PR merge; this session does not merge.
- Read the full ticket, specification, planning-map Notes, repository guidance
  and glossary, and canonical compatibility/workflow/build/qualification/plan
  resolutions. The specification approves the CLI-process seam and deterministic
  helper controls. No new product control or general subprocess framework was
  introduced. Untracked local guidance/files remain preserved and excluded.

## Delivered behavior and process ownership

The production C++ needed no change. `execv` replaces Pickaxe with the selected
Git in the same process ID, retaining cwd/environment/streams and status/signal
behavior. The baseline has no Pickaxe parent or owned child pipes to forward.
The portable input/byte logic remains ordinary C++20; `stat`/`access`/`execv`
are the narrow POSIX boundary. Test PTYs, local sockets, `/dev/fd`, and `ps` are
macOS evidence; Linux adaptation remains milestone 9.

RAII releases C++ argument/path storage on an ordinary launch-error return.
Successful exec replaces the address space without running those destructors.
Caller-owned descriptors stay inherited as in a direct Git launch; Pickaxe adds
none. Test context managers own/close control sockets, pipes, and PTY endpoints.
A failed test cleans up only its newly created process group.

The extended CLI tests establish:

- **Real Git cancellation:** before and after observable stdout, both via a
  process-group SIGINT and an actual PTY foreground Ctrl-C. Each runs against
  direct reference Git and through Pickaxe: **8 controlled scenarios**. A
  repository text-conversion helper sends PID/parent/group readiness over a
  local Unix socket and blocks awaiting control. A long newest commit message
  ensures captured output is observable despite stdio buffering. Cancellation
  happens after readiness, never after an arbitrary sleep.
- **Ownership and exit:** process-group inspection confirms Git and the helper
  are in the test group. After cancellation, stream EOF/status are observed,
  the helper socket reaches EOF, and `ps` confirms an empty group. Direct Git
  and Pickaxe terminate by SIGINT (`subprocess` status **-2**, conventionally
  130 as a shell status). Trace2 records exactly **one** Git search invocation
  per scenario; stderr has one Pickaxe fallback reason for Pickaxe and none for
  the direct reference. No retry, replacement search, or orphaned group remains.
- **Output boundary:** before-output cases observe **0 stdout bytes**; all
  after-output cases observe **32,926 bytes before SIGINT**. The final status is
  unsuccessful in both cases. Failed partial output is not reported as complete;
  its exact byte-equivalence remains outside the success contract.
- **Streams/descriptors/status:** a selected external executable receives binary
  stdin and forwards byte-identical stdout, with statuses **0 and 37**. It sees
  only descriptors 0/1/2 and the deliberately inherited caller descriptor,
  matching a direct launch. Captured streams reach EOF. Missing Git is **127**;
  unlaunchable Git is **126**, even with caller input connected. It emits no
  stdout and leaves no process retaining the pipes.
- **Basic handshake:** the original marker/polling cancellation test now uses a
  readiness pipe and bounded event wait, retaining the same-process-ID check.
  There are no `time.sleep` calls in the implemented cancellation checks.

Ctrl-C is foreground-process-group cancellation. Sending SIGINT solely to a
Git PID is a different operation and did not reliably stop a blocked converter
in the direct-Git investigation; no additional single-PID helper-supervision
promise is made. Future owned subprocesses require new lifetime/cleanup checks.

## Actual checks, diagnosis, and retained evidence

- Rebuilt using `cmake --build build`. The C++20 Release binary and its hash
  remain unchanged from #16/#17; no compiler/runtime/Git substitution occurred.
- Ran focused handshake, cancellation, descriptor, and launch-error checks.
  Initial fixture failures occurred with direct Git too. The first draft also
  misused `kqueue` as a context manager. It was removed; kernel process-exit
  monitoring was unnecessary for the final evidence.
- Used the diagnosing-bugs loop to isolate terminal exit: unread PTY echo of
  `^C` held the session leader in exit. Disabling echo while retaining `ISIG`
  and explicit VINTR fixed the isolated direct-Git case. Parent slave endpoints
  close promptly. Local sockets replaced draft FIFO controls; the final
  readiness observer uses `poll` and closes before cancellation. Full checks
  passed without changing production semantics or the oracle.
- Sandbox restrictions on `ps`/process control were reported, not counted as
  evidence. Final process tests ran with the necessary local access.
- A deliberately defective temporary wrapper ignored SIGINT and converted
  cancellation to exit zero. The new check rejected it with expected `0 != -2`,
  proving it detects false-success cancellation.
- **Full suite:** `ctest --test-dir build --output-on-failure -V` passed
  **1/1 CTest entries, 18/18 Python checks, no skips**. This reruns all implemented
  byte/status checks under the canonical full-rerun policy. The recorded run
  took 9.38 seconds. Observed signal-to-EOF/status durations for the eight small
  scenarios were roughly 0.0006–0.0024 seconds; these are fixture observations,
  not general latency promises.
- **Installed smoke:** Release installation into a disposable user-owned prefix
  passed matching search, real-Git cancellation, and stream/descriptor checks:
  **3/3 checks**, including all 8 cancellation scenarios. The prefix was removed.
- **Raw bundle:** [evidence/ticket-18.json.gz](evidence/ticket-18.json.gz) retains
  all 18 version-3 records, raw command/stream bytes, stdin, statuses, fixture and
  helper source hashes, executable hashes, effective config/refs, readiness and
  process-group evidence, Git traces, timing, CTest/installation logs, installed
  test records, and the expected negative-control failure. The gzip round trip
  and source hashes were verified. #17's older archive remains unchanged.
  No output normalization enters comparisons.

Reproduce on macOS with local PTY/process access:

```sh
cmake --build build
python3 tests/cli_baseline.py --pk ./build/pk \
  --evidence-dir ./build/evidence/cancellation \
  CliBaseline.test_real_git_cancellation_before_and_after_stdout \
  CliBaseline.test_streams_and_inherited_descriptor_ownership -v
ctest --test-dir build --output-on-failure -V
gzip -dc docs/implementation/evidence/ticket-18.json.gz > /tmp/pickaxe-ticket-18-evidence.json
```

## Code review and handoff

Independent Standards and Spec reviews are pending at the implementation commit.
Only #16/#17/#18 are included; PR #50 remains unmerged for owner review.

Next ticket: [#19 — M2 / T04 — Establish candidate containment on tiny histories](https://github.com/alifrahman2023/pickaxe/issues/19),
verified open and not started. Candidate containment/replay, indexing,
memory/publication audits, acceleration qualification, benchmarks, Linux
preparation, and two-platform release acceptance remain pending. The working
Git-backed CLI stays runnable; product acceleration remains disabled.
