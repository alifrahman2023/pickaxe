"""#22: disposable macOS publication experiment, never a product index."""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import platform
import selectors
import shutil
import signal
import subprocess
import tempfile
import unittest

OPTIONS = argparse.ArgumentParser()
OPTIONS.add_argument('--probe', type=Path, required=True)
OPTIONS.add_argument('--evidence-dir', type=Path)
ARGS, TEST_ARGS = OPTIONS.parse_known_args()
PROBE = ARGS.probe.resolve()
ROOT = Path(__file__).resolve().parents[1]
GIT = shutil.which('git')


class Publication(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pickaxe-publication-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.resource = self.root / 'resource'
        self.resource.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, LC_ALL='C', TZ='UTC')
        self.commands = []
        self.observations = []
        if ARGS.evidence_dir:
            self.addCleanup(self.save)

    def save(self):
        sources = ['tests/publication_protocol.py', 'tests/helpers/publication_probe.cpp']
        ARGS.evidence_dir.mkdir(parents=True, exist_ok=True)
        (ARGS.evidence_dir / (self._testMethodName + '.json')).write_text(json.dumps(dict(
            test=self.id(), version=1, platform=platform.platform(), resource=str(self.resource),
            git_sha256=hashlib.sha256(Path(GIT).read_bytes()).hexdigest(),
            probe_sha256=hashlib.sha256(PROBE.read_bytes()).hexdigest(),
            environment={k: v for k, v in self.env.items()
                         if k.startswith('GIT_') or k in ('PATH', 'LC_ALL', 'TZ', 'TMPDIR')},
            source_sha256={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources},
            commands=self.commands, observations=self.observations), indent=2) + '\n')

    def run_probe(self, mode, *args):
        command = [str(PROBE), mode, str(self.resource), *args]
        result = subprocess.run(command, cwd=self.root, env=self.env, capture_output=True, timeout=5)
        self.commands.append(dict(argv=command, status=result.returncode,
                                  stdout_hex=result.stdout.hex(), stderr_hex=result.stderr.hex()))
        return result

    def start_probe(self, mode, *args):
        command = [str(PROBE), mode, str(self.resource), *args]
        process = subprocess.Popen(command, cwd=self.root, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   env=self.env, start_new_session=True, bufsize=0)
        record = dict(argv=command, pid=process.pid, lines=[])
        self.commands.append(record)

        def cleanup():
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
            out, err = process.communicate(timeout=5)
            record.update(status=process.returncode, stdout_tail_hex=out.hex(), stderr_hex=err.hex())
        self.addCleanup(cleanup)
        return process, record

    def line(self, process, record):
        # Unbuffered pipe: select remains meaningful after each byte read.
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            data = b''
            while not data.endswith(b'\n'):
                self.assertTrue(selector.select(5), 'experiment did not reach checkpoint')
                byte = process.stdout.read(1)
                self.assertTrue(byte, 'experiment exited before checkpoint')
                data += byte
        record['lines'].append(data.decode())
        return data

    def test_stable_lock_rejects_writer_and_releases_after_death(self):
        holder, record = self.start_probe('hold-lock')
        self.assertEqual(self.line(holder, record), b'lock acquired\n')
        identity = (self.resource / 'writer.lock').stat().st_ino
        rejected = self.run_probe('publish')
        self.assertEqual(rejected.returncode, 3, rejected.stderr)
        self.assertIn(b'lock busy', rejected.stdout)
        self.assertEqual(list(self.resource.iterdir()), [self.resource / 'writer.lock'])
        holder.kill()
        self.assertEqual(holder.wait(timeout=5), -signal.SIGKILL)
        self.assertEqual(self.run_probe('try-lock').returncode, 0)
        self.assertEqual((self.resource / 'writer.lock').stat().st_ino, identity)
        self.observations.append(dict(lock_inode=identity, release='after SIGKILL; no power-loss claim'))

    def test_hardlink_replacement_and_old_open_reader(self):
        current = self.resource / 'current'
        current.write_bytes(b'old generation\n')
        with current.open('rb') as reader:
            old = os.fstat(reader.fileno())
            writer, record = self.start_probe('publish', 'pause-after-link')
            while self.line(writer, record) != b'checkpoint recovery-ready\n':
                pass
            backup = self.resource / 'recovery'
            self.assertEqual((backup.stat().st_dev, backup.stat().st_ino), (old.st_dev, old.st_ino))
            self.assertEqual(backup.stat().st_nlink, 2)
            self.assertEqual(current.read_bytes(), b'old generation\n')
            self.assertEqual(self.run_probe('try-lock').returncode, 3)
            writer.stdin.write(b'\n')
            writer.stdin.close()
            writer.stdin = None
            self.assertEqual(writer.wait(timeout=5), 0)
            record['lines'].extend(writer.stdout.read().decode().splitlines(keepends=True))
            self.assertEqual([line.strip() for line in record['lines']], [
                'lock acquired', 'open-directory ok', 'create-replacement ok',
                'replacement-cloexec ok', 'write ok', 'validate ok', 'replacement-fsync ok',
                'replacement-fullfsync ok', 'recovery-link ok', 'directory-before-fsync ok',
                'directory-before-fullfsync ok', 'checkpoint recovery-ready', 'rename ok',
                'directory-after-fsync ok', 'directory-after-fullfsync ok', 'commit confirmed',
                'cleanup-unlink ok', 'directory-cleanup-fsync ok', 'directory-cleanup-fullfsync ok',
                'state installed'])
            self.assertEqual(current.read_bytes(), b'new generation\n')
            self.assertNotEqual(current.stat().st_ino, old.st_ino)
            self.assertFalse(backup.exists())
            self.assertEqual(os.fstat(reader.fileno()).st_nlink, 0)
            self.assertEqual(reader.read(), b'old generation\n')
            self.observations.append(dict(old_inode=old.st_ino, old_device=old.st_dev,
                                          new_inode=current.stat().st_ino, old_reader_links=0,
                                          old_reader_hex=b'old generation\n'.hex()))

    def snapshot(self):
        files = {}
        for path in sorted(self.resource.iterdir()):
            info = path.stat()
            files[path.name] = dict(device=info.st_dev, inode=info.st_ino, links=info.st_nlink,
                                    bytes_hex=path.read_bytes().hex())
        self.observations.append(files)
        return files

    def test_failed_recovery_sync_preserves_prior_and_backup(self):
        (self.resource / 'current').write_bytes(b'old generation\n')
        result = self.run_probe('publish', 'directory-before-fullfsync')
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'failure directory-before-fullfsync errno {errno.EIO} injected'.encode(), result.stdout)
        self.assertIn(b'state precommit-preserved', result.stdout)
        self.assertNotIn(b'rename ok', result.stdout)
        files = self.snapshot()
        self.assertEqual(files['current']['bytes_hex'], b'old generation\n'.hex())
        self.assertEqual(files['current']['inode'], files['recovery']['inode'])
        self.assertEqual(len([n for n in files if n.startswith('replacement-')]), 1)

    def test_actual_sync_error_after_rename_reports_uncertainty(self):
        (self.resource / 'current').write_bytes(b'old generation\n')
        result = self.run_probe('publish', 'close-before-directory-after-fullfsync')
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'failure directory-after-fullfsync errno {errno.EBADF} actual'.encode(), result.stdout)
        self.assertIn(b'rename ok', result.stdout)
        self.assertIn(b'state publication-uncertain', result.stdout)
        self.assertNotIn(b'commit confirmed', result.stdout)
        files = self.snapshot()
        self.assertEqual(files['current']['bytes_hex'], b'new generation\n'.hex())
        self.assertEqual(files['recovery']['bytes_hex'], b'old generation\n'.hex())
        self.assertNotEqual(files['current']['inode'], files['recovery']['inode'])

    def test_postcommit_cleanup_error_is_installed_warning(self):
        (self.resource / 'current').write_bytes(b'old generation\n')
        result = self.run_probe('publish', 'cleanup-unlink')
        self.assertEqual(result.returncode, 0)
        self.assertIn(b'commit confirmed', result.stdout)
        self.assertIn(f'failure cleanup-unlink errno {errno.EIO} injected'.encode(), result.stdout)
        self.assertIn(b'state installed-cleanup-incomplete', result.stdout)
        files = self.snapshot()
        self.assertEqual(files['current']['bytes_hex'], b'new generation\n'.hex())
        self.assertEqual(files['recovery']['bytes_hex'], b'old generation\n'.hex())

    def test_git_helper_does_not_inherit_writer_lock(self):
        initialized = subprocess.run([GIT, 'init', '-q'], cwd=self.root, env=self.env,
                                     capture_output=True, timeout=5)
        self.assertEqual(initialized.returncode, 0, initialized.stderr)
        helper, record = self.start_probe('git-helper', GIT)
        self.assertEqual(self.line(helper, record), b'lock acquired\n')
        ready = self.line(helper, record)
        self.assertTrue(ready.startswith(b'helper '), ready)
        pid = int(ready.split()[1])
        os.kill(pid, 0)
        self.assertIsNone(helper.poll())
        self.assertEqual(self.run_probe('try-lock').returncode, 0)
        helper.stdin.write(b'helper still reading\n')
        helper.stdin.close()
        helper.stdin = None
        self.assertEqual(helper.wait(timeout=5), 0)
        self.observations.append(dict(git_helper_pid=pid, competing_writer='acquired while Git alive'))

    def test_initial_install_on_observed_local_apfs(self):
        filesystem = self.run_probe('inspect')
        self.assertEqual(filesystem.returncode, 0)
        self.assertIn(b'filesystem apfs\n', filesystem.stdout)
        self.assertIn(b'local yes\n', filesystem.stdout)
        result = self.run_probe('publish')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(b'directory-after-fullfsync ok\ncommit confirmed', result.stdout)
        self.assertIn(b'state installed', result.stdout)
        self.assertNotIn(b'recovery-link ok', result.stdout)
        files = self.snapshot()
        self.assertEqual(set(files), {'current', 'writer.lock'})
        self.assertEqual(files['current']['bytes_hex'], b'new generation\n'.hex())

    def test_unexplained_recovery_is_never_overwritten(self):
        (self.resource / 'current').write_bytes(b'old generation\n')
        (self.resource / 'recovery').write_bytes(b'unexplained evidence\n')
        before = self.snapshot()
        result = self.run_probe('publish')
        self.assertEqual(result.returncode, 1)
        self.assertIn(f'failure recovery-exists errno {errno.EEXIST} actual'.encode(), result.stdout)
        self.assertIn(b'state precommit-preserved', result.stdout)
        after = self.snapshot()
        self.assertEqual(before['current'], after['current'])
        self.assertEqual(before['recovery'], after['recovery'])
        self.assertFalse(any(n.startswith('replacement-') for n in after))


if __name__ == '__main__':
    unittest.main(argv=[__file__, *TEST_ARGS])
