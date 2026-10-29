"""Evidence validator contract: incomplete or inconsistent runs cannot pass."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
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
    def test_source_body_changed_during_self_tests_is_rejected_before_configure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'scripts').mkdir()
            (root / 'tests').mkdir()
            shutil.copyfile(CHECK.ROOT / 'scripts/check.py', root / 'scripts/check.py')
            (root / 'CMakeLists.txt').write_text('# fixture\n')
            (root / 'src').mkdir()
            (root / 'src/main.cpp').write_text('// before\n')
            (root / 'tests/check_evidence.py').write_text(
                'from pathlib import Path\nimport unittest\n'
                'class Fixture(unittest.TestCase):\n'
                ' def test_body(self):\n'
                '  p = Path(__file__).resolve().parents[1] / "src/main.cpp"\n'
                '  p.write_text("// changed\\n")\n'
                'if __name__ == "__main__": unittest.main()\n')
            result = subprocess.run([sys.executable, str(root / 'scripts/check.py'), 'run'],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'changed source: src/main.cpp', result.stderr)
            self.assertNotIn(b'+ cmake', result.stdout)
            self.assertFalse((root / 'build/checks/evidence/latest.json.gz').exists())

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
    def make_history(self, root, contents):
        repo = root / 'repo'
        subprocess.run(['git', 'init', '-q', '-b', 'benchmark', str(repo)], check=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                   GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                   GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid')
        for content in contents:
            (repo / 'file').write_bytes(content)
            subprocess.run(['git', 'add', 'file'], cwd=repo, env=env, check=True)
            subprocess.run(['git', 'commit', '-qm', 'fixture'], cwd=repo, env=env, check=True)
        return repo, env

    def test_validation_requires_cached_characterization(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env = self.make_history(root, [b'fixture\n'])
            output = root / 'shape.json'
            command = [sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                       'inspect', '--repo', str(repo), '--output', str(output)]
            result = subprocess.run(command, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0, 'validation silently characterized history')
            self.assertIn(b'--shape-manifest', result.stderr)
            self.assertFalse(output.exists())

    def test_inspect_complete_history_and_blob_volume(self):
        with tempfile.TemporaryDirectory() as directory:
            repo, env = self.make_history(Path(directory), [b'first\n', b'second\n'])
            subprocess.run(['git', '-C', str(repo), 'repack', '-ad'], env=env, check=True)
            output = Path(directory) / 'shape.json'
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'characterize', '--budget-seconds', '20', '--repo', str(repo), '--output', str(output)],
                                    capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            shape = json.loads(output.read_text())
            self.assertEqual((shape['commits'], shape['merges'], shape['root_commits'],
                              shape['unique_blob_bytes'], shape['unique_blobs']), (2, 0, 1, 13, 2))
            self.assertEqual(shape['attributes']['repository']['state'], 'absent')
            (repo / '.git/info/attributes').write_bytes(b'file -diff\n')
            subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                            'characterize', '--budget-seconds', '20', '--repo', str(repo), '--output', str(output)], check=True)
            changed = json.loads(output.read_text())
            self.assertEqual(changed['attributes']['repository']['state'], 'present')
            self.assertNotEqual(changed['attributes'], shape['attributes'])
            wrapper_dir = Path(directory) / 'bin'
            wrapper_dir.mkdir()
            real_git = subprocess.check_output(['which', 'git'], text=True).strip()
            wrapper = wrapper_dir / 'git'
            wrapper.write_text('#!' + sys.executable + '\nimport os, sys\n'
                               'if any(arg in ("rev-list", "cat-file") for arg in sys.argv):\n'
                               ' sys.exit("full graph scan attempted")\n'
                               'os.execv(' + repr(real_git) + ', [' + repr(real_git) + ', *sys.argv[1:]])\n')
            wrapper.chmod(0o755)
            fast_env = dict(env, PATH=str(wrapper_dir) + os.pathsep + os.environ['PATH'])
            validated = Path(directory) / 'validated.json'
            command = [sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'), 'validate',
                       '--repo', str(repo), '--shape-manifest', str(output), '--output', str(validated)]
            result = subprocess.run(command, env=fast_env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            reused = json.loads(validated.read_text())
            self.assertEqual({k: v for k, v in reused.items() if k != 'characterization_source'},
                             {k: v for k, v in changed.items() if k != 'characterization_source'})
            self.assertEqual(reused['characterization_source']['manifest_sha256'],
                             hashlib.sha256(output.read_bytes()).hexdigest())
            incomplete = Path(directory) / 'incomplete.json'
            for missing in ['head', 'config_hex', 'attributes', 'storage']:
                incomplete.write_text(json.dumps({k: v for k, v in changed.items() if k != missing}))
                invalid_command = list(command)
                invalid_command[invalid_command.index('--shape-manifest') + 1] = str(incomplete)
                result = subprocess.run(invalid_command, env=fast_env, capture_output=True)
                self.assertNotEqual(result.returncode, 0, 'incomplete cached shape was accepted: ' + missing)
            index = next((repo / '.git/objects/pack').glob('*.idx'))
            original_index = index.read_bytes()
            index.chmod(0o644)
            try:
                index.write_bytes(original_index + b'changed')
                result = subprocess.run(command, env=fast_env, capture_output=True)
                self.assertNotEqual(result.returncode, 0, 'changed object storage reused stale metrics')
            finally:
                index.write_bytes(original_index)
            subprocess.run(['git', '-C', str(repo), 'branch', 'extra'], check=True)
            result = subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                     'characterize', '--budget-seconds', '20', '--repo', str(repo), '--output', str(output)],
                                    capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'exactly refs/heads/benchmark', result.stderr)

    def test_freeze_preserves_newline_bytes_and_reproduces_reference(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env = self.make_history(root, [b'common-common\nalpha\nbeta\n', b'unique-a unique-b\n'])
            values = [('common', b'common'), ('common', b'common-'),
                      ('rare', b'unique-a'), ('rare', b'unique-b'),
                      ('zero-match', b'zero-a'), ('zero-match', b'zero-b'),
                      ('single-byte', b'c'), ('two-byte', b'co'), ('long', b'x' * 90),
                      ('spaces', b'unique-a unique-b'), ('unicode', 'é'.encode()),
                      ('newline', b'alpha\nbeta')]
            candidates = root / 'candidates.json'
            candidates.write_text(json.dumps([dict(id='q' + str(i), role=role, hex=value.hex())
                                              for i, (role, value) in enumerate(values)]))
            wrapper_dir = root / 'bin'
            wrapper_dir.mkdir()
            real_git = subprocess.check_output(['which', 'git'], text=True).strip()
            wrapper = wrapper_dir / 'git'
            calls, skip_completed = root / 'calls', root / 'skip-completed'
            wrapper.write_text('#!' + sys.executable + '\nimport os, sys, time\nfrom pathlib import Path\n'
                               'calls = Path(' + repr(str(calls)) + ')\n'
                               'if sys.argv[1:4] == ["--no-pager", "log", "--all"]:\n'
                               ' if Path(' + repr(str(skip_completed)) + ').exists() and "-Scommon-" in sys.argv:\n'
                               '  sys.exit("completed query rerun")\n'
                               ' fd = os.open(calls, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n'
                               ' os.write(fd, b"query\\n"); os.close(fd)\n'
                               ' deadline = time.monotonic() + 3\n'
                               ' while calls.read_bytes().count(b"\\n") < 2:\n'
                               '  if time.monotonic() > deadline: sys.exit("queries were not parallel")\n'
                               '  time.sleep(0.01)\n'
                               'os.execv(' + repr(real_git) + ', [' + repr(real_git) + ', *sys.argv[1:]])\n')
            wrapper.chmod(0o755)
            env['PATH'] = str(wrapper_dir) + os.pathsep + os.environ['PATH']
            shape = root / 'shape.json'
            subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                            'characterize', '--budget-seconds', '20', '--repo', str(repo), '--output', str(shape)], check=True, env=env)
            output = root / 'output'
            freeze_command = [sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                              'freeze', '--repo', str(repo), '--candidates', str(candidates),
                              '--output-dir', str(output), '--jobs', '2']
            preflight = subprocess.run(freeze_command + ['--shape-manifest', str(shape), '--preflight'],
                                       env=env, capture_output=True)
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            plan = json.loads(preflight.stdout)
            self.assertEqual(len(plan['commands']), 24)
            self.assertFalse(output.exists())
            self.assertFalse(calls.exists(), 'preflight launched a query')
            refused = subprocess.run(freeze_command + ['--shape-manifest', str(shape)],
                                     env=env, capture_output=True)
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(b'--budget-seconds', refused.stderr)
            self.assertFalse(output.exists())
            freeze_command += ['--budget-seconds', '20']
            result = subprocess.run(freeze_command + ['--shape-manifest', str(shape)], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            needles = json.loads((output / 'manifest.json').read_text())['needles']
            self.assertEqual([n['matches'] for n in needles], [2, 2, 1, 1, 0, 0, 2, 2, 0, 1, 0, 2])
            checkpoint = json.loads((output / 'manifest.partial.json').read_text())
            checkpoint['needles'] = [n for n in checkpoint['needles'] if n['id'] != 'q0']
            checkpoint['reproduced'] = [name for name in checkpoint['reproduced'] if name != 'q0']
            (output / 'manifest.partial.json').write_text(json.dumps(checkpoint))
            (output / 'manifest.json').unlink()
            (output / 'q0.stdout').write_bytes(b'interrupted capture\n')
            skip_completed.touch()
            retained = {p: p.read_bytes() for p in output.iterdir() if p.is_file()}
            before_calls = calls.read_bytes()
            preflight = subprocess.run(freeze_command + ['--resume', '--preflight'], env=env, capture_output=True)
            self.assertEqual(preflight.returncode, 0, preflight.stderr)
            plan = json.loads(preflight.stdout)
            self.assertEqual(len(plan['commands']), 2)
            self.assertEqual(len(plan['observed']), 11)
            self.assertEqual({p: p.read_bytes() for p in output.iterdir() if p.is_file()}, retained)
            self.assertEqual(calls.read_bytes(), before_calls)
            result = subprocess.run(freeze_command + ['--resume'], env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            resumed = json.loads((output / 'manifest.json').read_text())
            backup = output / resumed['resumed_from'][-1]['directory']
            self.assertEqual((backup / 'q0.stdout').read_bytes(), b'interrupted capture\n')
            self.assertEqual(resumed['needles'], needles)
            reference = subprocess.check_output(['git', '--no-pager', 'log', '--all', '-Salpha\nbeta', '--'],
                                                cwd=repo, env=env)
            self.assertEqual((output / 'q11.stdout').read_bytes(), reference)
            reproduced = root / 'reproduced'
            command = [sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'), 'reproduce',
                       '--repo', str(repo), '--frozen', str(output), '--output-dir', str(reproduced),
                       '--budget-seconds', '20']
            skip_completed.unlink()
            unsuitable = root / 'unsuitable.json'
            invalid_needles = json.loads(candidates.read_text())
            invalid_needles[4]['hex'] = b'common'.hex()
            unsuitable.write_text(json.dumps(invalid_needles))
            invalid_freeze = list(freeze_command)
            invalid_freeze[invalid_freeze.index('--candidates') + 1] = str(unsuitable)
            invalid_freeze[invalid_freeze.index('--output-dir') + 1] = str(root / 'unsuitable')
            result = subprocess.run(invalid_freeze + ['--shape-manifest', str(shape)], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            result = subprocess.run(invalid_freeze + ['--resume'], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0, 'resume accepted a matching zero-match candidate')
            self.assertFalse((root / 'unsuitable/manifest.json').exists())
            plan_command = command[:-2] + ['--preflight']
            plan_result = subprocess.run(plan_command, env=env, capture_output=True)
            self.assertEqual(plan_result.returncode, 0, plan_result.stderr)
            self.assertEqual(len(json.loads(plan_result.stdout)['commands']), 12)
            self.assertEqual(len(json.loads(plan_result.stdout)['observed']), 12)
            self.assertFalse(reproduced.exists())
            result = subprocess.run(command, env=env, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads((reproduced / 'verified.json').read_text())['byte_comparisons'], 24)
            (output / 'q0.stdout').write_bytes(b'changed retained output\n')
            command[command.index('--output-dir') + 1] = str(root / 'tampered')
            result = subprocess.run(command, env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'reference bytes did not reproduce', result.stderr)
            self.assertFalse((root / 'tampered/verified.json').exists())
            result = subprocess.run(command[:-2] + ['--preflight'], env=env, capture_output=True)
            self.assertNotEqual(result.returncode, 0, 'preflight accepted changed retained output')

    def test_budget_stops_parallel_git_readers(self):
        self.check_stopped_readers(budget=True)

    def test_parent_sigterm_stops_parallel_git_readers(self):
        self.check_stopped_readers(budget=False)

    def check_stopped_readers(self, budget):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            repo, env = self.make_history(root, [b'fixture\n'])
            bin_dir = root / 'bin'
            bin_dir.mkdir()
            real_git = subprocess.check_output(['which', 'git'], text=True).strip()
            shape = root / 'shape.json'
            subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                            'characterize', '--budget-seconds', '20', '--repo', str(repo), '--output', str(shape)], check=True, env=env)
            ready = root / 'readers'
            wrapper = bin_dir / 'git'
            wrapper.write_text('#!' + sys.executable + '\nimport os, sys, signal\n'
                               'if sys.argv[1:4] == ["--no-pager", "log", "--all"]:\n'
                               ' fd = os.open(' + repr(str(ready)) + ', os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)\n'
                               ' os.write(fd, (str(os.getpid()) + "\\n").encode()); os.close(fd)\n' +
                               (' signal.signal(signal.SIGTERM, signal.SIG_IGN)\n' if budget else '') +
                               ' os.read(0, 1)\n'
                               'os.execv(' + repr(real_git) + ', [' + repr(real_git) + ', *sys.argv[1:]])\n')
            wrapper.chmod(0o755)
            env['PATH'] = str(bin_dir) + os.pathsep + os.environ['PATH']
            process = subprocess.Popen([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                                        'freeze', '--repo', str(repo), '--candidates',
                                        str(CHECK.ROOT / 'benchmarks/git-needles.json'),
                                        '--output-dir', str(root / 'output'), '--jobs', '2',
                                        '--shape-manifest', str(shape), '--budget-seconds', '6' if budget else '20'],
                                       env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            readers = []
            try:
                deadline = time.monotonic() + 5
                while len(readers) < 2:
                    self.assertLess(time.monotonic(), deadline, 'parallel Git readers did not become ready')
                    if ready.exists():
                        readers = [int(pid) for pid in ready.read_text().splitlines()]
                    time.sleep(0.01)
                if not budget:
                    process.terminate()
                process.wait(timeout=8)
                self.assertNotEqual(process.returncode, 0)
                for pid in readers:
                    with self.assertRaises(ProcessLookupError, msg='reader survived parent SIGTERM'):
                        os.kill(pid, 0)
                if budget:
                    self.assertIn(b'budget exhausted', process.stdout.read())
                self.assertTrue((root / 'output/manifest.partial.json').exists())
                self.assertTrue((root / 'output/common-return.stdout').exists())
                self.assertFalse((root / 'output/manifest.json').exists())
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.communicate(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.communicate(timeout=5)

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


class ReferenceBaselines(unittest.TestCase):
    def fixture(self, root):
        repo, env = BenchmarkWorkloads().make_history(root, [b'a a rare\n', b'a rare\n'])
        shape_path = root / 'shape.json'
        subprocess.run([sys.executable, str(CHECK.ROOT / 'scripts/benchmarks.py'),
                        'characterize', '--budget-seconds', '20', '--repo', str(repo),
                        '--output', str(shape_path)], env=env, check=True)
        original, reproduced = root / 'original', root / 'reproduced'
        original.mkdir()
        reproduced.mkdir()
        records = []
        git_path = shutil.which('git')
        for name, role, needle, matches in [('common', 'common', b'a', 2),
                                            ('rare', 'rare', b'rare', 1),
                                            ('zero', 'zero-match', b'never', 0)]:
            result = subprocess.run([git_path, '--no-pager', 'log', '--all',
                                     '-S' + needle.decode(), '--'], cwd=repo, env=env,
                                    capture_output=True, check=True)
            record = dict(id=name, role=role, hex=needle.hex(), status=0,
                          matches=matches, stdout_bytes=len(result.stdout))
            for extension, data in [('stdout', result.stdout), ('stderr', result.stderr)]:
                for directory in [original, reproduced]:
                    (directory / name).with_suffix('.' + extension).write_bytes(data)
                record[extension + '_sha256'] = hashlib.sha256(data).hexdigest()
            records.append(record)
        manifest = original / 'manifest.json'
        manifest.write_text(json.dumps(dict(shape=json.loads(shape_path.read_text()),
            needles=records, git_path=git_path, git_sha256=CHECK.sha256(git_path))))
        audit = reproduced / 'verified.json'
        audit.write_text(json.dumps(dict(frozen_manifest_sha256=CHECK.sha256(manifest))))
        selection = root / 'selection.json'
        selection.write_text(json.dumps(dict(repo=str(repo),
            original_manifest=dict(path=str(manifest), sha256=CHECK.sha256(manifest)),
            audited_reproduction=dict(path=str(audit), sha256=CHECK.sha256(audit)),
            needles=[dict(c, original_base=str(original / c['id']),
                          reproduction_base=str(reproduced / c['id'])) for c in records])))
        command = [sys.executable, str(CHECK.ROOT / 'scripts/baselines.py'),
                   '--selection', str(selection), '--output-dir', str(root / 'baseline'),
                   '--activity-note', 'isolated tiny fixture']
        return command, selection

    def test_warm_samples_are_sequential_verified_and_ready_for_pairs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            pickaxe = root / 'pickaxe'
            pickaxe.write_text('#!' + sys.executable + '\nimport os, sys, time\n'
                'time.sleep(0.02)\n'
                'os.write(2, b"pk: Git fallback; acceleration is not enabled in this build\\n")\n'
                'os.execv(' + repr(shutil.which('git')) + ', ["git", "--no-pager", "log", '
                '"--all", "-S" + sys.argv[2], "--"])\n')
            pickaxe.chmod(0o755)
            result = subprocess.run(command + ['--budget-seconds', '20', '--pickaxe', str(pickaxe)],
                                    capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads((root / 'baseline/manifest.json').read_text())
            self.assertTrue(report['complete'])
            self.assertEqual(len(report['runs']), 36)
            self.assertEqual(report['cold']['status'], 'unavailable')
            self.assertIn('storage', report['hardware'])
            self.assertIn('workload', report['hardware']['storage'])
            self.assertIn('output', report['hardware']['storage'])
            common = [r for r in report['runs'] if r['id'] == 'common']
            self.assertEqual([(r['sample'], r['implementation']) for r in common],
                [(0, 'git'), (0, 'pickaxe'), (1, 'git'), (1, 'pickaxe'),
                 (2, 'pickaxe'), (2, 'git'), (3, 'git'), (3, 'pickaxe'),
                 (4, 'pickaxe'), (4, 'git'), (5, 'git'), (5, 'pickaxe')])
            for previous, following in zip(report['runs'], report['runs'][1:]):
                self.assertLessEqual(previous['finished_ns'], following['started_ns'])
            for record in report['runs']:
                self.assertEqual(record['status'], 0)
                self.assertTrue(record['bytes_verified'])
                if record['implementation'] == 'pickaxe':
                    self.assertEqual(Path(record['stderr']).read_bytes(),
                        b'pk: Git fallback; acceleration is not enabled in this build\n')
                if record['phase'] == 'warmup':
                    self.assertIsNone(record['elapsed_seconds'])
                elif record['implementation'] == 'pickaxe':
                    self.assertGreaterEqual(record['elapsed_seconds'], 0.02)
            for group in report['summary']:
                self.assertEqual(group['samples'], 5)
                self.assertLessEqual(group['min_seconds'], group['median_seconds'])
                self.assertLessEqual(group['median_seconds'], group['max_seconds'])

    def test_failed_command_retains_status_and_raw_files_without_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            pickaxe = root / 'failed-pickaxe'
            pickaxe.write_text('#!' + sys.executable + '\nimport os, sys\n'
                               'os.write(1, b"partial"); os.write(2, b"failure"); sys.exit(7)\n')
            pickaxe.chmod(0o755)
            result = subprocess.run(command + ['--budget-seconds', '20', '--pickaxe', str(pickaxe)],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0)
            output = root / 'baseline'
            self.assertFalse((output / 'manifest.json').exists())
            report = json.loads((output / 'manifest.partial.json').read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(report['runs'][-1]['status'], 7)
            self.assertFalse(report['runs'][-1]['bytes_verified'])
            self.assertEqual(Path(report['runs'][-1]['stdout']).read_bytes(), b'partial')
            self.assertEqual(Path(report['runs'][-1]['stderr']).read_bytes(), b'failure')

    def test_budget_stops_blocked_measurement_and_retains_partial_output(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            pickaxe, reader = root / 'blocked-pickaxe', root / 'reader'
            pickaxe.write_text('#!' + sys.executable + '\nimport os, signal, time\n'
                'signal.signal(signal.SIGTERM, signal.SIG_IGN)\n'
                'open(' + repr(str(reader)) + ', "w").write(str(os.getpid()))\n'
                'os.write(1, b"partial"); time.sleep(60)\n')
            pickaxe.chmod(0o755)
            result = subprocess.run(command + ['--budget-seconds', '4', '--pickaxe', str(pickaxe)],
                                    capture_output=True, timeout=10)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'budget exhausted', result.stderr)
            self.assertTrue(reader.exists(), 'budget expired before the fixture reader started')
            with self.assertRaises(ProcessLookupError):
                os.kill(int(reader.read_text()), 0)
            output = root / 'baseline'
            report = json.loads((output / 'manifest.partial.json').read_text())
            self.assertFalse(report['complete'])
            self.assertEqual(Path(report['current_command']['stdout']).read_bytes(), b'partial')
            interrupted = report['runs'][-1]
            self.assertTrue(interrupted['interrupted'])
            self.assertLess(interrupted['status'], 0)
            self.assertGreater(interrupted['interrupted_duration_seconds'], 0)
            self.assertFalse(interrupted['bytes_verified'])
            self.assertFalse((output / 'manifest.json').exists())

    def test_budget_stops_helper_after_reader_exits_on_sigterm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            ready, pickaxe = root / 'helper.json', root / 'parent-pickaxe'
            helper = ('import json, os, signal, time; '
                      'signal.signal(signal.SIGTERM, signal.SIG_IGN); '
                      'open(' + repr(str(ready)) + ', "w").write(json.dumps('
                      '{"pid":os.getpid(),"group":os.getpgrp()})); time.sleep(60)')
            pickaxe.write_text('#!' + sys.executable + '\nimport subprocess, sys, time\n'
                'from pathlib import Path\n'
                'subprocess.Popen([sys.executable, "-c", ' + repr(helper) + '])\n'
                'while not Path(' + repr(str(ready)) + ').exists(): time.sleep(0.01)\n'
                'time.sleep(60)\n')
            pickaxe.chmod(0o755)
            identity = None
            try:
                result = subprocess.run(command + ['--budget-seconds', '4', '--pickaxe', str(pickaxe)],
                                        capture_output=True, timeout=10)
                self.assertIn(b'budget exhausted', result.stderr)
                self.assertTrue(ready.exists(), 'helper did not start')
                identity = json.loads(ready.read_text())
                deadline = time.monotonic() + 1
                while True:
                    try:
                        os.kill(identity['pid'], 0)
                    except ProcessLookupError:
                        break
                    self.assertLess(time.monotonic(), deadline, 'helper survived its reader cancellation')
                    time.sleep(0.01)
                self.assertFalse((root / 'baseline/manifest.json').exists())
            finally:
                if identity is None and ready.exists():
                    identity = json.loads(ready.read_text())
                if identity is not None:
                    try:
                        os.killpg(identity['group'], signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_reproduction_budget_interrupts_creation_without_leaking_reader(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            manifest_path = root / 'original/manifest.json'
            manifest = json.loads(manifest_path.read_text())
            manifest['environment'] = dict(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                                          LC_ALL='C', TZ='UTC')
            manifest_path.write_text(json.dumps(manifest))
            reader = root / 'reader'
            # Inject a cancellation at the external Popen boundary, after a real
            # blocking child exists but before Popen returns it to the owner.
            runner = ('import os, runpy, signal, subprocess, sys\nfrom pathlib import Path\n'
                'real = subprocess.Popen\n'
                'def controlled(argv, *args, **kwargs):\n'
                ' if [os.fsdecode(a) for a in argv][1:4] == ["--no-pager", "log", "--all"]:\n'
                '  child = real([sys.executable, "-c", "import time; time.sleep(60)"], *args, **kwargs)\n'
                '  Path(' + repr(str(reader)) + ').write_text(str(child.pid))\n'
                '  os.kill(os.getpid(), signal.SIGALRM)\n'
                '  return child\n'
                ' return real(argv, *args, **kwargs)\n'
                'subprocess.Popen = controlled\n'
                'sys.argv = sys.argv[1:]\n'
                'runpy.run_path(sys.argv[0], run_name="__main__")\n')
            pid = None
            try:
                result = subprocess.run([sys.executable, '-c', runner,
                    str(CHECK.ROOT / 'scripts/benchmarks.py'), 'reproduce',
                    '--repo', str(root / 'repo'), '--frozen', str(root / 'original'),
                    '--output-dir', str(root / 'retry'), '--budget-seconds', '20'],
                    capture_output=True, timeout=10)
                self.assertIn(b'budget exhausted', result.stderr)
                self.assertTrue(reader.exists())
                pid = int(reader.read_text())
                with self.assertRaises(ProcessLookupError, msg='unregistered reader survived cancellation'):
                    os.kill(pid, 0)
                self.assertFalse((root / 'retry/verified.json').exists())
            finally:
                if pid is None and reader.exists():
                    pid = int(reader.read_text())
                if pid is not None:
                    try:
                        os.killpg(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass

    def test_changed_completed_capture_cannot_receive_completion_stamp(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            pickaxe = root / 'changing-pickaxe'
            pickaxe.write_text('#!' + sys.executable + '\nimport os, sys\nfrom pathlib import Path\n'
                'Path(' + repr(str(root / 'baseline/common-git-0.stdout')) + ').write_bytes(b"changed")\n'
                'os.execv(' + repr(shutil.which('git')) + ', ["git", "--no-pager", "log", '
                '"--all", "-S" + sys.argv[2], "--"])\n')
            pickaxe.chmod(0o755)
            result = subprocess.run(command + ['--budget-seconds', '20', '--pickaxe', str(pickaxe)],
                                    capture_output=True, timeout=30)
            self.assertNotEqual(result.returncode, 0, 'changed evidence accepted as complete')
            self.assertFalse((root / 'baseline/manifest.json').exists())
            self.assertTrue((root / 'baseline/manifest.partial.json').exists())

    def test_preflight_is_read_only_and_execution_requires_budget(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            command, selection = self.fixture(root)
            result = subprocess.run(command + ['--preflight'], capture_output=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            plan = json.loads(result.stdout)
            self.assertEqual(len(plan['commands']), 18)
            self.assertEqual(sum(c['phase'] == 'warmup' for c in plan['commands']), 3)
            self.assertFalse((root / 'baseline').exists())
            result = subprocess.run(command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn(b'--budget-seconds', result.stderr)
            self.assertFalse((root / 'baseline').exists())


if __name__ == '__main__':
    unittest.main()
