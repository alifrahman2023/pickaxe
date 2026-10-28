"""Milestone 1: observe the CLI against deterministic local reference Git."""

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pty
import shutil
import shlex
import selectors
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import unittest


OPTIONS = argparse.ArgumentParser()
OPTIONS.add_argument("--pk", required=True, type=Path)
OPTIONS.add_argument("--evidence-dir", type=Path,
                     help="retain commands, byte streams, and statuses as hexadecimal JSON")
ARGS, TEST_ARGS = OPTIONS.parse_known_args()
PK = str(ARGS.pk.resolve())
GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("tests require Git on inherited PATH")

LITERAL_NEEDLES = [
    ("one-byte", b"q"),
    ("two-byte", b"qr"),
    ("three-byte", b"qrs"),
    ("space", b" "),
    ("spaces", b"two words"),
    ("tab", b"\t"),
    ("tabs", b"left\tright"),
    ("newline", b"\n"),
    ("newlines", b"left\nright"),
    ("unicode-composed", "caf\u00e9".encode("utf-8")),
    ("unicode-decomposed", "cafe\u0301".encode("utf-8")),
    ("invalid-utf8", b"\xff\x80needle"),
    ("leading-hyphens", b"--all"),
    ("metacharacters", b"$(touch SHOULD_NOT_EXIST); * | & < > `touch ALSO_NOT_EXIST` ' \""),
]


class CliBaseline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pickaxe-cli-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.records = []
        self.observations = []
        if ARGS.evidence_dir is not None:
            self.addCleanup(self.save_evidence)
        # Isolate fixture construction, but give pk and its oracle identical inputs.
        self.env = {key: value for key, value in os.environ.items()
                    if not key.startswith("GIT_")}
        self.env.update({
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_AUTHOR_NAME": "Fixture",
            "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
            "GIT_COMMITTER_NAME": "Fixture",
            "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
            "GIT_AUTHOR_DATE": "2001-01-01T00:00:00+0000",
            "GIT_COMMITTER_DATE": "2001-01-01T00:00:00+0000",
            "LC_ALL": "C",
            "TZ": "UTC",
        })
        self.git("init", "-q")
        (self.repo / "content").write_bytes(b"needle x index\n")
        self.commit("root")
        (self.repo / "content").write_bytes(b"unchanged count: needle x index\n")
        self.commit("same count")
        (self.repo / "content").write_bytes(b"removed\n")
        self.commit("delete occurrences")

    def run_process(self, command, *, cwd=None, **kwargs):
        working_directory = self.repo if cwd is None else cwd
        result = subprocess.run(command, cwd=working_directory, env=self.env,
                                capture_output=True, timeout=5, **kwargs)
        self.record_result(command, result, cwd=working_directory, stdin=kwargs.get("input"))
        return result

    def record_result(self, command, result, *, cwd=None, stdin=None):
        self.records.append({
            "argv_hex": [os.fsencode(arg).hex() for arg in command],
            "cwd": str(self.repo if cwd is None else cwd),
            "environment": {key: value for key, value in self.env.items()
                            if key.startswith("GIT_") or key in ("PATH", "LC_ALL", "TZ")},
            "status": result.returncode,
            "stdin_hex": None if stdin is None else stdin.hex(),
            "stdout_hex": result.stdout.hex(),
            "stderr_hex": result.stderr.hex(),
        })

    def save_evidence(self):
        self.run_process([GIT, "config", "--show-origin", "--show-scope", "--list"])
        self.run_process([GIT, "show-ref", "--head"])
        bare = self.root / "bare.git"
        if bare.exists():
            self.run_process([GIT, "config", "--show-origin", "--show-scope", "--list"], cwd=bare)
            self.run_process([GIT, "show-ref", "--head"], cwd=bare)
        ARGS.evidence_dir.mkdir(parents=True, exist_ok=True)
        destination = ARGS.evidence_dir / (self._testMethodName + ".json")
        destination.write_text(json.dumps({
            "fixture_version": 3,
            "fixture_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "textconv_source_sha256": hashlib.sha256(
                (Path(__file__).parent / "helpers" / "controlled_textconv.py").read_bytes()).hexdigest(),
            "git_executable_sha256": hashlib.sha256(Path(GIT).read_bytes()).hexdigest(),
            "pk_executable_sha256": hashlib.sha256(Path(PK).read_bytes()).hexdigest(),
            "test": self.id(),
            "commands": self.records,
            "observations": self.observations,
        }, indent=2) + "\n")

    def git(self, *args):
        return self.run_process([GIT, *args], check=True)

    def commit(self, message, *paths):
        self.git("add", *(paths or ("content",)))
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", message)

    def compare_search(self, needle, *, cwd=None):
        # Pass bytes directly, including invalid UTF-8. No decoding or output
        # normalization is involved in the invocation or comparison.
        reference = self.run_process(
            [os.fsencode(GIT), b"--no-pager", b"log", b"--all", b"-S" + needle, b"--"], cwd=cwd)
        result = self.run_process([os.fsencode(PK), b"search", needle], cwd=cwd)
        self.assertEqual(result.returncode, reference.returncode)
        self.assertEqual(result.stdout, reference.stdout)
        self.assertTrue(result.stderr.startswith(b"pk: Git fallback;"))
        # The one extra line is Pickaxe's reason; Git diagnostics are unchanged.
        self.assertEqual(result.stderr.split(b"\n", 1)[1], reference.stderr)
        return reference

    def test_complete_matching_search(self):
        reference = self.git("--no-pager", "log", "--all", "-Sneedle", "--")
        self.assertIn(b"root", reference.stdout)
        self.assertIn(b"delete occurrences", reference.stdout)
        self.assertNotIn(b"same count", reference.stdout)
        result = self.run_process([PK, "search", "needle"])
        self.assertEqual(result.returncode, reference.returncode)
        self.assertEqual(result.stdout, reference.stdout)
        self.assertEqual(len(result.stderr.splitlines()), 1)
        self.assertIn(b"Git fallback", result.stderr)
        self.assertFalse((self.repo / ".git" / "pickaxe").exists())

    def test_zero_match_is_successful_empty_output(self):
        reference = self.git("--no-pager", "log", "--all", "-Szero-match-needle", "--")
        result = self.run_process([PK, "search", "zero-match-needle"])
        self.assertEqual((reference.returncode, reference.stdout), (0, b""))
        self.assertEqual((result.returncode, result.stdout), (0, b""))
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_short_and_metacharacter_arguments(self):
        metacharacters = "-$(touch SHOULD_NOT_EXIST); * [x] ' \""
        with (self.repo / "content").open("ab") as content:
            content.write(metacharacters.encode() + b"\n")
        self.commit("literal metacharacters")
        for needle in ["x", "index", metacharacters]:
            with self.subTest(needle=needle):
                reference = self.git("--no-pager", "log", "--all", "-S" + needle, "--")
                result = self.run_process([PK, "search", needle])
                self.assertTrue(reference.stdout)
                self.assertEqual(result.returncode, reference.returncode)
                self.assertEqual(result.stdout, reference.stdout)
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())

    def test_invalid_input_has_no_stdout(self):
        for operands in [[], ["search"], ["search", ""],
                         ["search", "one", "two"], ["index"], ["other", "needle"]]:
            with self.subTest(operands=operands):
                result = self.run_process([PK, *operands])
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"")
                self.assertIn(b"nonempty literal needle", result.stderr)

    def test_missing_git(self):
        self.env["PATH"] = str(self.root / "no-git")
        result = self.run_process([PK, "search", "needle"])
        self.assertEqual(result.returncode, 127)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"git", result.stderr)

    def selected_git(self, source):
        directory = self.root / "selected-bin"
        directory.mkdir()
        selected = directory / "git"
        selected.write_text(source)
        selected.chmod(0o755)
        self.env["PATH"] = str(directory) + os.pathsep + self.env.get("PATH", "")
        return selected

    def test_unlaunchable_selected_git_does_not_try_another(self):
        self.selected_git("This is not an executable format.\n")
        result = self.run_process([PK, "search", "needle"], input=b"caller input\x00\xff")
        self.assertEqual(result.returncode, 126)
        self.assertEqual(result.stdout, b"")
        self.assertIn(b"cannot launch git", result.stderr)

    def test_selected_git_status_is_preserved(self):
        self.selected_git("#!/bin/sh\nprintf 'partial output'; exit 37\n")
        result = self.run_process([PK, "search", "needle"])
        self.assertEqual(result.returncode, 37)
        self.assertEqual(result.stdout, b"partial output")
        self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_real_git_failure_is_preserved(self):
        outside = self.root / "outside"
        outside.mkdir()
        reference = self.run_process([GIT, "--no-pager", "log", "--all", "-Sneedle", "--"],
                                     cwd=outside)
        result = self.run_process([PK, "search", "needle"], cwd=outside)
        self.assertNotEqual(reference.returncode, 0)
        self.assertEqual(result.returncode, reference.returncode)
        self.assertEqual(result.stdout, reference.stdout)

    def test_effective_configuration_environment_and_cwd(self):
        self.git("config", "format.pretty", "format:%C(auto)%h%C(reset) %s")
        self.git("config", "color.ui", "always")
        subdirectory = self.repo / "nested"
        subdirectory.mkdir()
        self.env.update(GIT_CONFIG_COUNT="1", GIT_CONFIG_KEY_0="log.abbrevCommit",
                        GIT_CONFIG_VALUE_0="true")
        reference = self.run_process([GIT, "--no-pager", "log", "--all", "-Sneedle", "--"],
                                     cwd=subdirectory)
        result = self.run_process([PK, "search", "needle"], cwd=subdirectory)
        self.assertEqual(reference.returncode, 0)
        self.assertIn(b"\x1b[", reference.stdout)
        self.assertEqual((result.returncode, result.stdout),
                         (reference.returncode, reference.stdout))
        self.assertFalse((self.repo / ".git" / "pickaxe").exists())

    def test_literal_argument_bytes(self):
        for label, needle in LITERAL_NEEDLES:
            (self.repo / label).write_bytes(needle + b"\n")
            self.commit("add " + label, label)
        for label, needle in LITERAL_NEEDLES:
            with self.subTest(label=label, needle_hex=needle.hex()):
                reference = self.compare_search(needle)
                self.assertEqual(reference.returncode, 0)
                self.assertTrue(reference.stdout)
        self.assertFalse((self.repo / "SHOULD_NOT_EXIST").exists())
        self.assertFalse((self.repo / "ALSO_NOT_EXIST").exists())
        self.assertFalse((self.repo / ".git" / "pickaxe").exists())

    def test_selected_git_receives_exact_argument_bytes(self):
        # The local Git may interpret Unicode according to its own effective
        # configuration. Independently observe the bytes Pickaxe gives it.
        self.selected_git(
            "#!" + sys.executable + "\n"
            "import os, sys\n"
            "sys.stdout.buffer.write(b'\\0'.join(os.fsencode(arg) for arg in sys.argv[1:]))\n"
        )
        for label, needle in LITERAL_NEEDLES:
            with self.subTest(label=label, needle_hex=needle.hex()):
                result = self.run_process([os.fsencode(PK), b"search", needle])
                self.assertEqual(result.returncode, 0)
                self.assertEqual(result.stdout, b"--no-pager\0log\0--all\0-S" + needle + b"\0--")
                self.assertEqual(len(result.stderr.splitlines()), 1)

    def test_occurrence_counts_instead_of_matching_lines(self):
        for message, content in [
            ("introduce token", b"token before\nanchor\n"),
            ("move line without count change", b"anchor\ntoken after\n"),
            ("increase token count", b"anchor\ntoken token after\n"),
            ("decrease token count", b"anchor\ntoken after\n"),
        ]:
            (self.repo / "content").write_bytes(content)
            self.commit(message)
        reference = self.compare_search(b"token")
        self.assertEqual(reference.returncode, 0)
        for message in [b"introduce token", b"increase token count", b"decrease token count"]:
            self.assertIn(message, reference.stdout)
        self.assertNotIn(b"move line without count change", reference.stdout)
        line_search = self.git("--no-pager", "log", "--all", "-Gtoken", "--")
        self.assertIn(b"move line without count change", line_search.stdout)

    def test_nul_is_blob_data(self):
        (self.repo / "content").write_bytes(b"before\x00binary-needle\x00after\n")
        self.commit("binary addition")
        (self.repo / "content").write_bytes(b"before\x00after\n")
        self.commit("binary deletion")
        reference = self.compare_search(b"binary-needle")
        self.assertEqual(reference.returncode, 0)
        self.assertIn(b"binary addition", reference.stdout)
        self.assertIn(b"binary deletion", reference.stdout)
        # No attempt is made to put NUL in argv: the operating-system CLI
        # cannot represent it. The needle above searches blobs containing NUL.

    def test_bare_repository_complete_fallback_leaves_resources_untouched(self):
        # Keep a match reachable only through a non-HEAD branch.
        self.git("checkout", "-qb", "side")
        (self.repo / "content").write_bytes(b"side-only-needle\n")
        self.commit("side branch match")
        self.git("checkout", "-")
        bare = self.root / "bare.git"
        self.git("clone", "--bare", str(self.repo), str(bare))
        self.run_process([GIT, "config", "format.pretty", "format:%C(auto)%h%C(reset) %s %d"],
                         cwd=bare, check=True)
        self.run_process([GIT, "config", "color.ui", "always"], cwd=bare, check=True)
        self.assertEqual(self.run_process([GIT, "rev-parse", "--is-bare-repository"],
                                         cwd=bare, check=True).stdout, b"true\n")
        for needle in [b"needle", b"side-only-needle", b"zero-match-needle"]:
            reference = self.compare_search(needle, cwd=bare)
            self.assertEqual(reference.returncode, 0)
            if needle != b"zero-match-needle":
                self.assertTrue(reference.stdout)
                self.assertIn(b"\x1b[", reference.stdout)
        resource = bare / "pickaxe"
        self.assertFalse(resource.exists())
        # A pre-existing unusable resource must also remain byte-for-byte and
        # metadata-identical. Its contents cannot be mistaken for no matches.
        resource.mkdir()
        sentinel = resource / "unusable-index"
        sentinel.write_bytes(b"not a completed index\x00\xff")
        before = (resource.stat(), sentinel.stat(), sentinel.read_bytes())
        reference = self.compare_search(b"side-only-needle", cwd=bare)
        self.assertEqual(reference.returncode, 0)
        self.assertIn(b"side branch match", reference.stdout)
        after = (resource.stat(), sentinel.stat(), sentinel.read_bytes())
        # Exclude access time, which the test's own reads may update.
        for old, new in zip(before[:2], after[:2]):
            self.assertEqual((old.st_ino, old.st_mode, old.st_size, old.st_mtime_ns),
                             (new.st_ino, new.st_mode, new.st_size, new.st_mtime_ns))
        self.assertEqual(before[2], after[2])
        self.assertEqual(list(resource.iterdir()), [sentinel])

    def test_real_git_failure_after_output_is_unsuccessful(self):
        helper = self.root / "controlled_textconv.py"
        helper.write_text(
            "import pathlib, sys\n"
            "content = pathlib.Path(sys.argv[1]).read_bytes()\n"
            "if b'needle x index' in content:\n"
            "    sys.stderr.write('controlled textconv failure\\n')\n"
            "    sys.exit(23)\n"
            "sys.stdout.buffer.write(content)\n"
        )
        (self.repo / ".gitattributes").write_text("content diff=controlled\n")
        (self.repo / "content").write_bytes(b"needle latest\n")
        self.commit("latest match before failure", "content", ".gitattributes")
        self.git("config", "diff.controlled.textconv",
                 shlex.join([sys.executable, str(helper)]))
        reference = self.compare_search(b"needle")
        self.assertNotEqual(reference.returncode, 0)
        self.assertIn(b"latest match before failure", reference.stdout)
        self.assertIn(b"controlled textconv failure", reference.stderr)

    def test_streams_and_inherited_descriptor_ownership(self):
        caller_file = self.root / "caller-owned"
        caller_file.write_bytes(b"caller descriptor")
        selected = self.selected_git("")
        payload = b"unchanged pipe bytes\x00\xff\n"
        with caller_file.open("rb") as inherited:
            for status in (0, 37):
                with self.subTest(status=status):
                    selected.write_text(
                        "#!" + sys.executable + "\n"
                        "import json, os, sys\n"
                        "descriptors = []\n"
                        "for name in os.listdir('/dev/fd'):\n"
                        "    try: os.fstat(int(name))\n"
                        "    except OSError: continue\n"
                        "    descriptors.append(int(name))\n"
                        "sys.stdout.buffer.write(sys.stdin.buffer.read())\n"
                        "sys.stderr.write(json.dumps(sorted(descriptors)) + '\\n')\n"
                        "sys.exit(" + str(status) + ")\n"
                    )
                    command = [str(selected), "--no-pager", "log", "--all", "-Sneedle", "--"]
                    reference = self.run_process(command, input=payload, pass_fds=(inherited.fileno(),))
                    result = self.run_process([PK, "search", "needle"], input=payload,
                                              pass_fds=(inherited.fileno(),))
                    self.assertEqual(reference.returncode, status)
                    self.assertEqual(reference.stdout, payload)
                    self.assertEqual(json.loads(reference.stderr), [0, 1, 2, inherited.fileno()])
                    self.assertEqual((result.returncode, result.stdout), (status, payload))
                    self.assertTrue(result.stderr.startswith(b"pk: Git fallback;"))
                    self.assertEqual(result.stderr.split(b"\n", 1)[1], reference.stderr)
                    self.observations.append({
                        "forwarded_status": status, "caller_descriptor": inherited.fileno(),
                        "selected_git_descriptors": json.loads(reference.stderr),
                        "stdin_eof_and_stdout_stderr_eof_observed": True,
                    })

    def test_real_git_cancellation_before_and_after_stdout(self):
        (self.repo / ".gitattributes").write_text("content diff=controlled\n")
        (self.repo / "content").write_bytes(b"needle newest\n")
        # More than a stdio buffer ensures observable output even when Git's
        # captured log output is buffered. The event loop drains it concurrently.
        self.commit("observable newest match " + "x" * 32768, "content", ".gitattributes")
        helper = Path(__file__).parent / "helpers" / "controlled_textconv.py"
        reference_statuses = {}
        for phase in ("before", "after"):
            for delivery in ("group", "terminal"):
                for program in ("git", "pk"):
                    with self.subTest(phase=phase, delivery=delivery, program=program):
                        result = self.cancel_real_search(helper, phase, delivery, program)
                        if program == "git":
                            reference_statuses[phase, delivery] = result
                        else:
                            self.assertEqual(result, reference_statuses[phase, delivery])

    def cancel_real_search(self, helper, phase, delivery, program):
        directory = self.root / (phase + "-" + delivery + "-" + program)
        directory.mkdir()
        trace_path = directory / "trace.json"
        command = ([GIT, "--no-pager", "log", "--all", "-Sneedle", "--"]
                   if program == "git" else [PK, "search", "needle"])
        with contextlib.ExitStack() as resources:
            # Keep the local socket path below macOS's sockaddr_un path limit.
            control_directory = resources.enter_context(tempfile.TemporaryDirectory(prefix="pk18-", dir="/tmp"))
            socket_path = str(Path(control_directory) / "control")
            server = resources.enter_context(socket.socket(socket.AF_UNIX))
            server.bind(socket_path)
            server.listen(1)
            self.git("config", "diff.controlled.textconv", shlex.join(
                [sys.executable, str(helper), socket_path, phase]))
            self.env["GIT_TRACE2_EVENT"] = str(trace_path)
            terminal_options = {}
            if delivery == "terminal":
                master_fd, slave_fd = pty.openpty()
                master = resources.enter_context(os.fdopen(master_fd, "wb", buffering=0))
                slave = resources.enter_context(os.fdopen(slave_fd, "rb", buffering=0))
                terminal_settings = termios.tcgetattr(slave.fileno())
                terminal_settings[3] &= ~(termios.ECHO | termios.ECHONL)
                terminal_settings[3] |= termios.ISIG
                terminal_settings[6][termios.VINTR] = b"\x03"
                termios.tcsetattr(slave.fileno(), termios.TCSANOW, terminal_settings)

                def claim_terminal():
                    # Popen has already created the new session and duplicated
                    # the slave onto stdin when this child-only hook runs.
                    fcntl.ioctl(0, termios.TIOCSCTTY, 0)

                terminal_options = {"stdin": slave, "preexec_fn": claim_terminal}
            else:
                terminal_options = {"stdin": subprocess.DEVNULL}
            process = subprocess.Popen(command, cwd=self.repo, env=self.env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       start_new_session=True, **terminal_options)
            if delivery == "terminal":
                slave.close()
            captured = {"stdout": bytearray(), "stderr": bytearray(), "events": bytearray()}
            ready = None
            try:
                selector = resources.enter_context(selectors.PollSelector())
                for stream, name in [(process.stdout, "stdout"), (process.stderr, "stderr"),
                                     (server, "connection")]:
                    selector.register(stream, selectors.EVENT_READ, name)
                deadline = time.monotonic() + 5
                while ready is None or (phase == "after" and not captured["stdout"]):
                    notifications = selector.select(timeout=max(0, deadline - time.monotonic()))
                    self.assertTrue(notifications, "Git/textconv did not reach cancellation point")
                    for key, _ in notifications:
                        if key.data == "connection":
                            connection, _ = server.accept()
                            resources.enter_context(connection)
                            selector.unregister(server)
                            selector.register(connection, selectors.EVENT_READ, "events")
                            continue
                        chunk = os.read(key.fd, 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                        captured[key.data].extend(chunk)
                    if b"\n" in captured["events"]:
                        ready = json.loads(captured["events"].split(b"\n", 1)[0])
                self.assertEqual(ready["event"], "ready")
                self.assertEqual(ready["group"], process.pid)
                group_command = ["/bin/ps", "-g", str(process.pid),
                                 "-o", "pid=,ppid=,pgid=,stat=,comm="]
                membership = self.run_process(group_command, check=True)
                member_pids = {int(line.split()[0]) for line in membership.stdout.splitlines()}
                self.assertTrue({process.pid, ready["pid"]}.issubset(member_pids))
                if phase == "before":
                    self.assertFalse(captured["stdout"])
                else:
                    self.assertIn(b"observable newest match", captured["stdout"])
                selector.close()
                stdout_before_signal = bytes(captured["stdout"])
                cancel_started = time.monotonic()
                if delivery == "terminal":
                    self.assertEqual(os.tcgetpgrp(master.fileno()), process.pid)
                    master.write(b"\x03")  # Terminal VINTR: Ctrl-C to foreground group.
                else:
                    os.killpg(process.pid, signal.SIGINT)
                stdout, stderr = process.communicate(timeout=5)
                cancellation_seconds = time.monotonic() - cancel_started
                captured["stdout"].extend(stdout)
                captured["stderr"].extend(stderr)
                self.assertEqual(process.returncode, -signal.SIGINT)
                connection.settimeout(5)
                self.assertEqual(connection.recv(1), b"", "textconv kept its control socket open")
                if phase == "before":
                    self.assertFalse(captured["stdout"])
                groups = self.run_process(group_command)
                self.assertIn(groups.returncode, (0, 1))
                self.assertEqual(groups.stderr, b"")
                remaining = groups.stdout.splitlines()
                self.assertEqual(remaining, [], "search left an orphaned process")
                trace = [json.loads(line) for line in trace_path.read_text().splitlines()]
                starts = [entry for entry in trace if entry["event"] == "start"]
                self.assertEqual(len(starts), 1, "search retried or launched replacement Git")
                reason = b"pk: Git fallback;"
                self.assertEqual(captured["stderr"].count(reason), int(program == "pk"))
                self.record_result(command, subprocess.CompletedProcess(
                    command, process.returncode, bytes(captured["stdout"]), bytes(captured["stderr"])))
                self.observations.append({
                    "phase": phase, "delivery": delivery, "program": program,
                    "search_pid": process.pid, "helper_ready": ready,
                    "helper_ready_hex": bytes(captured["events"]).hex(),
                    "helper_exit_observed": True, "remaining_group": [],
                    "seconds_from_signal_to_eof_and_status": cancellation_seconds,
                    "git_trace": trace, "stdout_before_signal_hex": stdout_before_signal.hex(),
                })
                return process.returncode
            finally:
                self.env.pop("GIT_TRACE2_EVENT", None)
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.communicate(timeout=5)

    def test_basic_cancellation_of_selected_git(self):
        # An explicit pipe notification replaces the original marker polling.
        with contextlib.ExitStack() as resources:
            read_fd, write_fd = os.pipe()
            ready = resources.enter_context(os.fdopen(read_fd, "rb", buffering=0))
            writer = resources.enter_context(os.fdopen(write_fd, "wb", buffering=0))
            self.selected_git(
                "#!" + sys.executable + "\n"
                "import os, signal\n"
                "signal.signal(signal.SIGINT, signal.SIG_DFL)\n"
                "os.write(" + str(write_fd) + ", str(os.getpid()).encode())\n"
                "os.close(" + str(write_fd) + ")\n"
                "signal.pause()\n"
            )
            process = subprocess.Popen([PK, "search", "needle"], cwd=self.repo, env=self.env,
                                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                       pass_fds=(write_fd,))
            writer.close()
            try:
                selector = resources.enter_context(selectors.PollSelector())
                selector.register(ready, selectors.EVENT_READ)
                self.assertTrue(selector.select(timeout=5), "selected Git never became ready")
                self.assertEqual(int(ready.read(64)), process.pid)
                process.send_signal(signal.SIGINT)
                stdout, stderr = process.communicate(timeout=5)
                self.record_result(process.args, subprocess.CompletedProcess(
                    process.args, process.returncode, stdout, stderr))
                self.assertEqual(process.returncode, -signal.SIGINT)
                self.assertEqual(stdout, b"")
                self.assertEqual(len(stderr.splitlines()), 1)
            finally:
                if process.poll() is None:
                    process.kill()
                process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(argv=[__file__, *TEST_ARGS])
