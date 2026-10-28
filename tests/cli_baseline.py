"""Ticket #16: observe the CLI against a deterministic local reference Git."""

import argparse
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import unittest


OPTIONS = argparse.ArgumentParser()
OPTIONS.add_argument("--pk", required=True, type=Path)
ARGS, TEST_ARGS = OPTIONS.parse_known_args()
PK = str(ARGS.pk.resolve())
GIT = shutil.which("git")
if GIT is None:
    raise RuntimeError("tests require Git on inherited PATH")


class CliBaseline(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="pickaxe-cli-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
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

    def run_process(self, command, **kwargs):
        return subprocess.run(command, cwd=self.repo, env=self.env,
                              capture_output=True, timeout=5, **kwargs)

    def git(self, *args):
        return self.run_process([GIT, *args], check=True)

    def commit(self, message):
        self.git("add", "content")
        self.git("-c", "commit.gpgsign=false", "commit", "-qm", message)

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
        self.assertNotEqual(result.returncode, 0)
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
        result = self.run_process([PK, "search", "needle"])
        self.assertNotEqual(result.returncode, 0)
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
        reference = subprocess.run([GIT, "--no-pager", "log", "--all", "-Sneedle", "--"],
                                   cwd=outside, env=self.env, capture_output=True, timeout=5)
        result = subprocess.run([PK, "search", "needle"], cwd=outside,
                                env=self.env, capture_output=True, timeout=5)
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
        reference = subprocess.run([GIT, "--no-pager", "log", "--all", "-Sneedle", "--"],
                                   cwd=subdirectory, env=self.env, capture_output=True, timeout=5)
        result = subprocess.run([PK, "search", "needle"], cwd=subdirectory,
                                env=self.env, capture_output=True, timeout=5)
        self.assertEqual(reference.returncode, 0)
        self.assertIn(b"\x1b[", reference.stdout)
        self.assertEqual((result.returncode, result.stdout),
                         (reference.returncode, reference.stdout))
        self.assertFalse((self.repo / ".git" / "pickaxe").exists())

    def test_basic_cancellation_of_selected_git(self):
        # A controlled external executable makes readiness deterministic. This
        # does not replace #18's real-Git/helper/terminal cancellation evidence.
        marker = self.root / "ready"
        self.selected_git(
            "#!" + sys.executable + "\n"
            "import os, signal\n"
            "signal.signal(signal.SIGINT, signal.SIG_DFL)\n"
            "with open(" + repr(str(marker)) + ", 'w') as ready:\n"
            "    ready.write(str(os.getpid()))\n"
            "signal.pause()\n"
        )
        process = subprocess.Popen([PK, "search", "needle"], cwd=self.repo, env=self.env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            deadline = time.monotonic() + 5
            while not marker.exists() or not marker.read_text():
                if time.monotonic() >= deadline or process.poll() is not None:
                    self.fail("selected Git never became ready")
                time.sleep(0.01)
            self.assertEqual(int(marker.read_text()), process.pid)
            process.send_signal(signal.SIGINT)
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, -signal.SIGINT)
            self.assertEqual(stdout, b"")
            self.assertEqual(len(stderr.splitlines()), 1)
        finally:
            if process.poll() is None:
                process.kill()
            process.communicate(timeout=5)


if __name__ == "__main__":
    unittest.main(argv=[__file__, *TEST_ARGS])
