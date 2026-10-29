"""Evidence validator contract: incomplete or inconsistent runs cannot pass."""
import importlib.util
import json
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import tempfile
import time
import unittest

SPEC = importlib.util.spec_from_file_location('check', Path(__file__).resolve().parents[1] / 'scripts/check.py')
CHECK = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


class EvidenceValidation(unittest.TestCase):
    def setUp(self):
        self.bundle = dict(
            schema=2, ctest_status=0, tool_test_status=0,
            expected_tool_tests=['ToolFixture.test_example'],
            tool_test_log='Ran 1 test in 0.1s\n\nOK\n',
            junit='<testsuite>' + ''.join(f'<testcase name="{group}"/>' for group in CHECK.SUITES) + '</testsuite>',
            ctest_log='Ran 1 test in 0.1s\nOK\n' * len(CHECK.SUITES),
            expected_tests={group: ['Fixture.test_example'] for group in CHECK.SUITES},
            sources={path: 'original' for path in [*CHECK.SUITES.values(), 'tests/helpers/controlled_textconv.py',
                                                                 'tests/fixtures/candidate_model.py',
                                                                 'tests/fixtures/ordered_replay.py',
                                                                 'tests/helpers/publication_probe.cpp']},
            source_root='/historical/checkout', git_sha256='git', pk_sha256='pk',
            publication_probe_sha256='probe',
            records={
                'cli_baseline': [dict(test='__main__.Fixture.test_example',
                                      fixture_source_sha256='original', textconv_source_sha256='original',
                                      git_executable_sha256='git', pk_executable_sha256='pk')],
                'candidate_containment': [dict(test='__main__.Fixture.test_example', git_sha256='git',
                                              source_sha256={'tests/candidate_containment.py': 'original',
                                                             'tests/fixtures/candidate_model.py': 'original',
                                                             'tests/fixtures/ordered_replay.py': 'original'})],
                'publication_protocol': [dict(test='__main__.Fixture.test_example', git_sha256='git',
                                             probe_sha256='probe',
                                             source_sha256={'tests/publication_protocol.py': 'original',
                                                            'tests/helpers/publication_probe.cpp': 'original'})]})

    def test_historical_bundle_does_not_require_current_checkout_hashes(self):
        self.assertEqual(CHECK.verify(self.bundle), len(CHECK.SUITES))
        with self.assertRaisesRegex(ValueError, 'changed source'):
            CHECK.verify(self.bundle, current_sources=True)

    def test_missing_record_is_rejected(self):
        self.bundle['records']['cli_baseline'].clear()
        with self.assertRaisesRegex(ValueError, 'incomplete/duplicate'):
            CHECK.verify(self.bundle)

    def test_duplicate_record_is_rejected(self):
        self.bundle['records']['cli_baseline'] *= 2
        with self.assertRaisesRegex(ValueError, 'incomplete/duplicate'):
            CHECK.verify(self.bundle)

    def test_empty_candidate_hash_map_is_rejected(self):
        self.bundle['records']['candidate_containment'][0]['source_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'source metadata incomplete'):
            CHECK.verify(self.bundle)

    def test_partial_candidate_hash_map_is_rejected(self):
        del self.bundle['records']['candidate_containment'][0]['source_sha256']['tests/fixtures/candidate_model.py']
        with self.assertRaisesRegex(ValueError, 'source metadata incomplete'):
            CHECK.verify(self.bundle)

    def test_wrong_source_hash_is_rejected(self):
        self.bundle['sources']['tests/cli_baseline.py'] = 'different'
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            CHECK.verify(self.bundle)

    def test_missing_publication_cpp_hash_is_rejected(self):
        del self.bundle['records']['publication_protocol'][0]['source_sha256']['tests/helpers/publication_probe.cpp']
        with self.assertRaisesRegex(ValueError, 'source metadata incomplete'):
            CHECK.verify(self.bundle)

    def test_changed_publication_cpp_hash_is_rejected(self):
        self.bundle['records']['publication_protocol'][0]['source_sha256']['tests/helpers/publication_probe.cpp'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'source hash mismatch'):
            CHECK.verify(self.bundle)

    def test_wrong_publication_binary_is_rejected(self):
        self.bundle['records']['publication_protocol'][0]['probe_sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'probe binary hash mismatch'):
            CHECK.verify(self.bundle)

    def test_failed_run_is_rejected_even_with_complete_records(self):
        self.bundle['ctest_status'] = 1
        with self.assertRaisesRegex(ValueError, 'CTest failed'):
            CHECK.verify(self.bundle)

    def test_skipped_tool_self_tests_are_rejected(self):
        self.bundle['tool_test_log'] = 'Ran 1 test in 0.1s\n\nOK (skipped=1)\n'
        with self.assertRaisesRegex(ValueError, 'self-tests skipped'):
            CHECK.verify(self.bundle)

    def test_missing_or_zero_tool_execution_is_rejected(self):
        for log in ('', 'Ran 0 tests in 0.1s\n\nOK\n'):
            with self.subTest(log=log):
                self.bundle['tool_test_log'] = log
                with self.assertRaisesRegex(ValueError, 'self-test execution count'):
                    CHECK.verify(self.bundle)

    def test_partial_tool_execution_is_rejected(self):
        self.bundle['expected_tool_tests'].append('ToolFixture.test_another')
        with self.assertRaisesRegex(ValueError, 'self-test execution count'):
            CHECK.verify(self.bundle)

    def test_incomplete_tool_summary_is_rejected(self):
        self.bundle['tool_test_log'] = 'Ran 1 test in 0.1s\n'
        with self.assertRaisesRegex(ValueError, 'completion summary'):
            CHECK.verify(self.bundle)

    def test_empty_tool_inventory_is_rejected(self):
        self.bundle['expected_tool_tests'] = []
        self.bundle['tool_test_log'] = 'Ran 0 tests in 0.1s\n\nOK\n'
        with self.assertRaisesRegex(ValueError, 'self-test inventory'):
            CHECK.verify(self.bundle)

    def test_skipped_checks_are_rejected(self):
        self.bundle['ctest_log'] = 'Ran 1 test in 0.1s\nOK (skipped=1)'
        with self.assertRaisesRegex(ValueError, 'skips'):
            CHECK.verify(self.bundle)


class CommandStreaming(unittest.TestCase):
    def test_live_output_and_log_before_exit_preserve_bytes_and_failure_status(self):
        with tempfile.TemporaryDirectory(prefix='pickaxe-command-stream-') as temp:
            log = Path(temp) / 'command.log'
            child = ('import os, sys; os.write(1, b"\\xffprogress"); '
                     'os.write(2, b"\\x00diagnostic"); sys.stdin.buffer.read(1); '
                     'os.write(1, b"\\ncomplete\\n"); sys.exit(7)')
            runner = ('import pathlib, runpy, sys; '
                      'check = runpy.run_path(sys.argv[1]); '
                      'sys.exit(check["execute"]([sys.executable, "-u", "-c", sys.argv[3]], '
                      'pathlib.Path(sys.argv[2])))')
            process = subprocess.Popen([sys.executable, '-u', '-c', runner,
                                        str(CHECK.ROOT / 'scripts/check.py'), str(log), child],
                                       stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            prefix = b'\xffprogress\x00diagnostic'
            observed = b''
            try:
                deadline = time.monotonic() + 5
                with selectors.DefaultSelector() as selector:
                    selector.register(process.stdout, selectors.EVENT_READ)
                    while prefix not in observed:
                        remaining = deadline - time.monotonic()
                        self.assertGreater(remaining, 0, 'output buffered until child exit')
                        self.assertTrue(selector.select(remaining), 'output buffered until child exit')
                        chunk = os.read(process.stdout.fileno(), 65536)
                        self.assertTrue(chunk, 'runner exited before live output')
                        observed += chunk
                self.assertIsNone(process.poll(), 'child must still be waiting for input')
                self.assertEqual(log.read_bytes(), prefix)
            finally:
                try:
                    tail, _ = process.communicate(input=b'\n', timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.communicate(timeout=5)
                    raise
            self.assertEqual(process.returncode, 7)
            self.assertTrue((observed + tail).endswith(prefix + b'\ncomplete\n'))
            self.assertEqual(log.read_bytes(), prefix + b'\ncomplete\n')


class BenchmarkWorkloads(unittest.TestCase):
    def test_inspect_complete_history_and_blob_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'repo'
            subprocess.run(['git', 'init', '-q', '-b', 'benchmark', str(repo)], check=True)
            env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                       GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
            for content in [b'first\n', b'second\n']:
                (repo / 'file').write_bytes(content)
                subprocess.run(['git', 'add', 'file'], cwd=repo, env=env, check=True)
                subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=repo, env=env, check=True)
            output = Path(directory) / 'shape.json'
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'inspect', '--repo', str(repo), '--output', str(output)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            shape = json.loads(output.read_text())
            self.assertEqual((shape['commits'], shape['merges'], shape['root_commits'],
                              shape['unique_blob_bytes'], shape['unique_blobs']), (2, 0, 1, 13, 2))
            self.assertEqual(shape['attributes']['repository']['state'], 'absent')
            (repo / '.git/info/attributes').write_bytes(b'file -diff\n')
            subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                            'inspect', '--repo', str(repo), '--output', str(output)], check=True)
            changed = json.loads(output.read_text())
            self.assertEqual(changed['attributes']['repository']['state'], 'present')
            self.assertNotEqual(changed['attributes'], shape['attributes'])
            subprocess.run(['git', '-C', str(repo), 'branch', 'extra'], check=True)
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'inspect', '--repo', str(repo), '--output', str(output)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'exactly refs/heads/benchmark', result.stderr)

    def test_freeze_preserves_newline_bytes_and_reproduces_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo = root / 'repo'
            subprocess.run(['git', 'init', '-q', '-b', 'benchmark', str(repo)], check=True)
            env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
            env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                       GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                       GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
            for content in [b'common-common\nalpha\nbeta\n', b'unique-a unique-b\n']:
                (repo / 'file').write_bytes(content)
                subprocess.run(['git', 'add', 'file'], cwd=repo, env=env, check=True)
                subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=repo, env=env, check=True)
            values = [('common', b'common'), ('common', b'common-'),
                      ('rare', b'unique-a'), ('rare', b'unique-b'),
                      ('zero-match', b'zero-a'), ('zero-match', b'zero-b'),
                      ('single-byte', b'c'), ('two-byte', b'co'), ('long', b'x' * 90),
                      ('spaces', b'unique-a unique-b'), ('unicode', 'é'.encode()),
                      ('newline', b'alpha\nbeta')]
            candidates = root / 'candidates.json'
            candidates.write_text(json.dumps([dict(id='q' + str(i), role=role, hex=value.hex())
                                              for i, (role, value) in enumerate(values)]))
            output = root / 'output'
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'freeze', '--repo', str(repo), '--candidates', str(candidates),
                                     '--output-dir', str(output)], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            needles = json.loads((output / 'manifest.json').read_text())['needles']
            self.assertEqual([n['matches'] for n in needles], [2, 2, 1, 1, 0, 0, 2, 2, 0, 1, 0, 2])
            reference = subprocess.check_output(['git', '--no-pager', 'log', '--all', '-Salpha\nbeta', '--'],
                                                cwd=repo, env=env)
            self.assertEqual((output / 'q11.stdout').read_bytes(), reference)
            reproduced = root / 'reproduced'
            command = [sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'), 'reproduce',
                       '--repo', str(repo), '--frozen', str(output), '--output-dir', str(reproduced)]
            result = subprocess.run(command, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((reproduced / 'verified.json').read_text())['byte_comparisons'], 24)
            (output / 'q0.stdout').write_bytes(b'changed retained output\n')
            command[-1] = str(root / 'tampered')
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'reference bytes did not reproduce', result.stderr)
            self.assertFalse((root / 'tampered/verified.json').exists())

    def test_freeze_reserves_reproduction_capture_names(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            candidates = root / 'candidates.json'
            candidates.write_text(json.dumps([dict(id='q0-reproduced', role='rare', hex='61')]))
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'freeze', '--repo', str(root), '--candidates', str(candidates),
                                     '--output-dir', str(root / 'output')], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'reserved reproduction suffix', result.stderr)

    def test_freeze_rejects_empty_and_nul_argument_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for value in ['', '610062']:
                candidates = root / 'candidates.json'
                candidates.write_text(json.dumps([dict(id='invalid', role='long', hex=value)]))
                result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                         'freeze', '--repo', str(root), '--candidates', str(candidates),
                                         '--output-dir', str(root / 'output')], capture_output=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'nonempty bytes without NUL', result.stderr)


if __name__ == '__main__':
    unittest.main()
