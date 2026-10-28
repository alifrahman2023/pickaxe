"""Ticket #19: independent Git oracles at the approved candidate-trace seam."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import sys
import tempfile
import unittest

from fixtures.candidate_model import CandidateModel

OPTIONS = argparse.ArgumentParser()
OPTIONS.add_argument('--evidence-dir', type=Path)
ARGS, TEST_ARGS = OPTIONS.parse_known_args()
GIT = shutil.which('git')
if GIT is None:
    raise RuntimeError('Git is required on inherited PATH')


class Containment(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='pickaxe-containment-')
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        self.env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
        self.env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
                        GIT_AUTHOR_NAME='Fixture', GIT_AUTHOR_EMAIL='fixture@example.invalid',
                        GIT_COMMITTER_NAME='Fixture', GIT_COMMITTER_EMAIL='fixture@example.invalid',
                        GIT_AUTHOR_DATE='2001-01-01T00:00:00+0000',
                        GIT_COMMITTER_DATE='2001-01-01T00:00:00+0000', LC_ALL='C', TZ='UTC')
        self.commands = []
        self.traces = []
        self.git('init', '-q', '--initial-branch=main')
        if ARGS.evidence_dir:
            self.addCleanup(self.save)

    def git(self, *args, input=None, cwd=None):
        result = subprocess.run([GIT, *args], cwd=cwd or self.repo, env=self.env,
                                input=input, capture_output=True, timeout=10)
        self.commands.append(dict(argv_hex=[os.fsencode(a).hex() for a in [GIT, *args]],
                                  cwd=str(cwd or self.repo), stdin_hex=None if input is None else input.hex(),
                                  status=result.returncode, stdout_hex=result.stdout.hex(),
                                  stderr_hex=result.stderr.hex()))
        if result.returncode:
            raise RuntimeError(f'Git failed: {args!r}: {result.stderr!r}')
        return result.stdout

    def save(self):
        self.git('config', '--show-origin', '--show-scope', '--list')
        self.git('show-ref', '--head')
        ARGS.evidence_dir.mkdir(parents=True, exist_ok=True)
        sources = [Path(__file__), Path(__file__).parent / 'fixtures/candidate_model.py']
        (ARGS.evidence_dir / (self._testMethodName + '.json')).write_text(json.dumps(dict(
            version=1, test=self.id(), git=GIT,
            git_sha256=hashlib.sha256(Path(GIT).read_bytes()).hexdigest(),
            source_sha256={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources},
            environment={k: v for k, v in self.env.items()
                         if k.startswith('GIT_') or k in ('PATH', 'LC_ALL', 'TZ')},
            commands=self.commands, traces=self.traces), indent=2) + '\n')

    def commit(self, name, files):
        for path, data in files.items():
            target = self.repo / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if data is None:
                target.unlink()
            else:
                target.write_bytes(data)
        self.git('add', '-A')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', name)
        return self.git('rev-parse', 'HEAD').strip().decode()

    def check(self, model, needle, **kwargs):
        # Git determines matches, independently of model extraction/postings.
        matches = self.git('--no-pager', 'log', '--all', '--format=%H',
                           b'-S' + needle, '--').decode().splitlines()
        trace = model.query(needle, **kwargs)
        trace['reference_matches'] = matches
        self.traces.append(trace)
        self.assertTrue(set(matches) <= set(trace['candidates']), trace)
        return trace

    def snapshot(self, commit):
        # Independent oracle: compare full trees by pathname, mode and object ID.
        # No diff-tree records or model postings participate in expected values.
        entries = {}
        for entry in self.git('ls-tree', '-r', '-z', '--full-tree', commit).split(b'\0'):
            if entry:
                meta, path = entry.split(b'\t', 1)
                mode, kind, oid = meta.split()
                entries[path] = (mode, kind, oid.decode())
        return entries

    def check_associations(self, model):
        expected = {}
        always = set()
        for row in self.git('rev-list', '--all', '--parents').decode().splitlines():
            commit, *parents = row.split()
            if commit not in model.coverage:
                continue
            if len(parents) > 1:
                always.add(commit)
                continue
            old = self.snapshot(parents[0]) if parents else {}
            new = self.snapshot(commit)
            for path in old.keys() | new.keys():
                if old.get(path) == new.get(path):
                    continue
                for entry in (old.get(path), new.get(path)):
                    if entry is None:
                        continue
                    mode, kind, oid = entry
                    if kind == b'blob':
                        expected.setdefault(oid, set()).add(commit)
                    elif mode == b'160000':
                        always.add(commit)
        self.assertEqual(dict(model.associations), expected)
        self.assertEqual(model.always, always)

    def test_special_contents_renames_copies_and_subdirectory(self):
        root = self.commit('contents', {'space name': b'outside-edited-line\nneedle\n',
                                      'binary\tname': b'\0binary-needle\xff',
                                      'new\nline': b'abcdef old',
                                      'sub/anchor': b'unchanged'})
        os.symlink('symlink-needle', self.repo / 'link')
        self.commit('symlink', {})
        os.rename(self.repo / 'space name', self.repo / 'renamed')
        rename = self.commit('pure rename', {})
        (self.repo / 'copy').write_bytes((self.repo / 'renamed').read_bytes())
        self.commit('copy and rename edit', {'renamed': b'outside-edited-line\nneedle\nedit\n'})
        (self.repo / 'link').unlink()
        self.commit('type and executable mode', {'link': b'regular-needle'})
        (self.repo / 'copy').chmod(0o755)
        self.commit('mode', {})
        self.commit('deletions', {'binary\tname': None, 'new\nline': None, 'copy': None})
        # Suppressing extraction settings are overridden only on internal helpers.
        self.git('config', 'diff.renames', 'copies')
        self.git('config', 'diff.relative', 'true')
        self.git('config', 'diff.ignoreSubmodules', 'all')
        self.git('config', 'diff.external', '/definitely/missing/external-diff')
        before = self.git('config', '--list')
        model = CandidateModel(self.git, cwd=self.repo / 'sub')
        self.check_associations(model)
        for needle in [b'needle', b'binary-needle', b'symlink-needle', b'abcdef',
                       b'outside-edited-line']:
            self.check(model, needle)
        self.assertEqual(before, self.git('config', '--list'))
        self.assertIn(root, self.check(model, b'binary-needle')['candidates'])
        trace = self.check(model, b'needle')
        self.assertIn(rename, trace['candidates'])
        self.assertNotIn(rename, trace['reference_matches'])

    def test_blob_intersection_repetition_and_chunk_boundaries(self):
        split = self.commit('split across blobs', {'left': b'qwer', 'right': b'erty'})
        repeated = self.commit('false positive', {'repeat': b'aaa', 'order': b'abc--bcd--cde'})
        boundary = self.commit('boundaries', {'boundary': b'123456' + 'caf\u00e9'.encode() + b'XYZ',
                                            'repeated': b'aaaaa'})
        model = CandidateModel(self.git, chunk_size=7)
        self.check_associations(model)
        trace = self.check(model, b'qwerty')
        self.assertNotIn(split, trace['candidates'])
        self.assertEqual(trace['matching_blobs'], [])
        for needle in [b'6caf', 'caf\u00e9XYZ'.encode(), b'aaaaa']:
            self.assertIn(boundary, self.check(model, needle)['reference_matches'])
        trace = self.check(model, b'aaaa')
        self.assertIn(repeated, trace['candidates'])  # aaa has the sole distinct trigram
        self.assertNotIn(repeated, trace['reference_matches'])
        self.assertIn(boundary, trace['reference_matches'])
        trace = self.check(model, b'abcde')
        self.assertIn(repeated, trace['candidates'])  # order is deliberately unproven
        self.assertNotIn(repeated, trace['reference_matches'])

    def test_merges_gitlinks_unindexed_and_out_of_scope(self):
        root = self.commit('root', {'content': b'root-needle'})
        self.git('branch', 'side')
        main = self.commit('main', {'content': b'main-needle'})
        self.git('checkout', '-q', 'side')
        side = self.commit('side', {'side': b'side-needle'})
        self.git('checkout', '-q', 'main')
        tree = self.git('rev-parse', main + '^{tree}').strip()
        merge = self.git('commit-tree', tree, '-p', main, '-p', side,
                         input=b'two-parent merge\n').strip().decode()
        self.git('reset', '--hard', merge)
        for name, oid in [('gitlink addition', root), ('gitlink update', side)]:
            self.git('update-index', '--add', '--cacheinfo', '160000,' + oid + ',module')
            self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', name)
        self.git('update-index', '--force-remove', 'module')
        self.git('-c', 'commit.gpgsign=false', 'commit', '-qm', 'gitlink deletion')
        tip = self.git('rev-parse', 'HEAD').strip().decode()
        octopus = self.git('commit-tree', tree, '-p', tip, '-p', main, '-p', side,
                           input=b'octopus merge\n').strip().decode()
        self.git('reset', '--hard', octopus)
        model = CandidateModel(self.git)
        self.check_associations(model)
        self.assertTrue({merge, octopus} <= model.always)
        self.assertEqual(len(model.always), 5)  # two merges and three gitlink changes
        synthesized = self.check(model, b'Subproject commit ' + root.encode())
        self.assertTrue(synthesized['reference_matches'])
        self.git('config', 'diff.ignoreSubmodules', 'all')
        suppressed = CandidateModel(self.git)
        self.check_associations(suppressed)
        self.assertEqual(model.always, suppressed.always)
        self.assertEqual(dict(model.associations), dict(suppressed.associations))
        # An older branch arrives after coverage is frozen. Age is not coverage.
        self.env['GIT_AUTHOR_DATE'] = self.env['GIT_COMMITTER_DATE'] = '1990-01-01T00:00:00+0000'
        blob = self.git('hash-object', '-w', '--stdin', input=b'older-needle').strip()
        older_tree = self.git('mktree', input=b'100644 blob ' + blob + b'\told\n').strip()
        older = self.git('commit-tree', older_tree, input=b'older uncovered\n').strip().decode()
        self.git('update-ref', 'refs/heads/older-fetched', older)
        for needle in [b'older-needle', b'root-needle', b'not-present', b'Subproject commit ' + root.encode()]:
            trace = self.check(model, needle)
            self.assertIn(older, trace['candidates'])
            self.assertTrue(model.always <= set(trace['candidates']))
            self.assertEqual(len(trace['candidates']), len(set(trace['candidates'])))
        # Retain stored associations but remove their only current refs/HEADs.
        self.git('checkout', '-q', 'older-fetched')
        self.git('branch', '-D', 'main', 'side')
        trace = self.check(model, b'root-needle')
        self.assertEqual(trace['candidates'], [older])
        self.assertNotIn(root, trace['scope'])

    def test_text_conversion_is_outside_raw_content_argument(self):
        root = self.commit('raw', {'content': b'raw-before'})
        self.commit('raw change', {'content': b'raw-after'})
        converter = self.repo / '.git' / 'converter.py'
        converter.write_text("import pathlib,sys\np=pathlib.Path(sys.argv[1]).read_bytes()\n"
                             "sys.stdout.buffer.write(b'converted-only' if p == b'raw-before' else b'other')\n")
        (self.repo / '.git' / 'info' / 'attributes').write_text('content diff=fixture\n')
        self.git('config', 'diff.fixture.textconv', shlex.join([sys.executable, str(converter)]))
        model = CandidateModel(self.git)
        self.check_associations(model)
        trace = model.query(b'converted-only')
        matches = self.git('log', '--all', '--format=%H', '-Sconverted-only', '--').decode().splitlines()
        self.assertIn(root, matches)
        self.assertEqual(trace['candidates'], [])
        trace.update(path='unsupported-textconv-observation', reference_matches=matches,
                     conclusion='raw proof invalid; whole-search Git fallback required')
        self.traces.append(trace)

    def test_complete_sides_and_deletions(self):
        root = self.commit('root', {'content': b'needle old\n'})
        new = self.commit('new', {'content': b'needle needle new\n'})
        deletion = self.commit('delete', {'content': None, 'other': b'unrelated\n'})
        unrelated = self.commit('known nonmatching covered commit', {'other': b'still unrelated\n'})
        model = CandidateModel(self.git)
        self.check_associations(model)
        trace = self.check(model, b'needle')
        self.assertEqual(set(trace['candidates']), {root, new, deletion})
        self.assertNotIn(unrelated, trace['candidates'])
        self.assertEqual(set(trace['reference_matches']), {root, new, deletion})
        empty = self.check(model, b'zero-match-needle')
        self.assertEqual(empty['candidates'], [])
        self.assertEqual(empty['reference_matches'], [])
        for short in (b'q', b'qr'):
            with self.assertRaisesRegex(ValueError, 'whole-search Git fallback'):
                model.query(short)


if __name__ == '__main__':
    unittest.main(argv=[sys.argv[0], *TEST_ARGS])
