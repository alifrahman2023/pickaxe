#!/usr/bin/env python3
"""Frozen, local source-history workloads. Development tooling, not product indexing."""
import argparse
import filecmp
import hashlib
import heapq
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PINS = {
    'git': ('https://github.com/git/git.git',
            '39bf06adf96da25b87c9aa7d35a32ef3683eb4a4',
            '777489f9e09c8d0dd6b12f9d90de6376330577a2'),
    'linux': ('https://github.com/torvalds/linux.git',
              '98f7e32f20d28ec452afb208f9cffc08448a2652',
              'adc218676eef25575469234709c2d87185ca223a'),
}
GIT = shutil.which('git')


def environment():
    # Deliberately declared benchmark configuration; same for every reference/paired run.
    env = {k: v for k, v in os.environ.items() if not k.startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull,
               GIT_TERMINAL_PROMPT='0', LC_ALL='C', TZ='UTC')
    return env


def git(repo, *args, **kwargs):
    return subprocess.run([GIT, '-C', str(repo), *args], env=environment(),
                          check=True, stdout=subprocess.PIPE, **kwargs).stdout


def digest(path):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def inspect(repo):
    repo = Path(repo).resolve()
    common = Path(os.fsdecode(git(repo, 'rev-parse', '--git-common-dir').strip()))
    if not common.is_absolute():
        common = repo / common
    if (common / 'shallow').exists() or (common / 'objects/info/alternates').exists():
        raise ValueError('workload must have complete independent object storage')
    refs = git(repo, 'for-each-ref', '--format=%(refname) %(objectname)').decode().splitlines()
    head = git(repo, 'rev-parse', 'HEAD').decode().strip()
    if refs != ['refs/heads/benchmark ' + head]:
        raise ValueError('workload requires exactly refs/heads/benchmark at HEAD')
    if git(repo, 'symbolic-ref', 'HEAD').strip() != b'refs/heads/benchmark':
        raise ValueError('HEAD must point to benchmark branch')
    worktrees = git(repo, 'worktree', 'list', '--porcelain').decode()
    if worktrees.count('worktree ') != 1:
        raise ValueError('linked worktrees are forbidden')
    if git(repo, 'status', '--porcelain', '--untracked-files=all'):
        raise ValueError('workload checkout is dirty')
    config = git(repo, 'config', '--null', '--list', '--show-origin')
    if b'partialclone' in config.lower() or b'promisor' in config.lower():
        raise ValueError('partial repositories are forbidden')
    commits = merges = roots = parent_edges = max_parents = 0
    with tempfile.TemporaryFile() as traversal:
        subprocess.run([GIT, '-C', str(repo), 'rev-list', '--all', '--parents'],
                       env=environment(), stdout=traversal, check=True)
        traversal.seek(0)
        for line in traversal:
            parents = len(line.split()) - 1
            commits += 1
            merges += parents > 1
            roots += parents == 0
            parent_edges += parents
            max_parents = max(max_parents, parents)
    counts, sizes, largest = {}, {}, []
    with tempfile.TemporaryFile() as objects, tempfile.TemporaryFile() as inventory:
        subprocess.run([GIT, '-C', str(repo), 'rev-list', '--objects', '--all', '--no-object-names'],
                       env=environment(), stdout=objects, check=True)
        objects.seek(0)
        subprocess.run([GIT, '-C', str(repo), 'cat-file',
                        '--batch-check=%(objectname) %(objecttype) %(objectsize)'],
                       env=environment(), stdin=objects, stdout=inventory, check=True)
        inventory.seek(0)
        for line in inventory:
            oid, kind, size = line.decode().split()
            size = int(size)
            counts[kind] = counts.get(kind, 0) + 1
            sizes[kind] = sizes.get(kind, 0) + size
            if kind == 'blob':
                heapq.heappush(largest, (size, oid))
                if len(largest) > 10:
                    heapq.heappop(largest)
    total = 0
    with tempfile.TemporaryFile() as inventory:
        subprocess.run([GIT, '-C', str(repo), 'cat-file', '--batch-all-objects',
                        '--batch-check=%(objectname)', '--unordered'],
                       env=environment(), stdout=inventory, check=True)
        inventory.seek(0)
        total = sum(1 for _ in inventory)
    packs = [{ 'name': p.name, 'bytes': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted((common / 'objects/pack').glob('*.pack'))]
    return dict(head=head, refs=refs, symbolic_head='refs/heads/benchmark', worktrees=worktrees,
                commits=commits, merges=merges, root_commits=roots, parent_edges=parent_edges,
                max_parents=max_parents, reachable_objects=counts, reachable_bytes=sizes,
                unique_blobs=counts.get('blob', 0), unique_blob_bytes=sizes.get('blob', 0),
                largest_blobs=sorted(largest, reverse=True), total_objects=total,
                out_of_scope_objects=total - sum(counts.values()), packs=packs,
                packed_object_bytes=sum(p['bytes'] for p in packs),
                count_objects=git(repo, 'count-objects', '-v').decode(), config_hex=config.hex())


def prepare(root, name):
    root = root.resolve()
    source = root / 'sources' / (name + '.git')
    url, a, b = PINS[name]
    # The network acquisition is explicit and can be resumed before preparation.
    if not source.exists():
        raise ValueError(f'first: git init --bare {source}; git -C {source} fetch --no-tags {url} {b}')
    git(source, 'fsck', '--full', '--no-reflogs')
    for label, oid in [('A', a), ('B', b)]:
        repo = root / (name + '-' + label)
        repo.mkdir()  # Refuse to overwrite any existing attempt.
        git(repo, 'init', '-q', '-b', 'benchmark')
        # Private copies: no alternates, no upstream refs, no shared writable packs.
        shutil.copytree(source / 'objects', repo / '.git/objects', dirs_exist_ok=True)
        git(repo, 'config', 'gc.auto', '0')
        git(repo, 'config', 'core.autocrlf', 'false')
        git(repo, 'config', 'log.date', 'default')
        git(repo, 'config', 'color.ui', 'false')
        git(repo, 'config', 'format.pretty', 'medium')
        git(repo, 'config', 'log.decorate', 'false')
        git(repo, 'update-ref', 'refs/heads/benchmark', oid)
        git(repo, 'reset', '--hard', oid)
        shape = inspect(repo)
        save(root / (name + '-' + label + '.json'), dict(
            source_url=url, pinned_commit=oid, preparation='complete B fetch; private object copy; checkout A/B; no repack',
            shape=shape))
        print(name, label, shape['commits'], shape['unique_blob_bytes'], flush=True)


def reference(repo, needle, output):
    with output.with_suffix('.stdout').open('wb') as stdout, output.with_suffix('.stderr').open('wb') as stderr:
        result = subprocess.run([os.fsencode(GIT), b'--no-pager', b'log', b'--all', b'-S' + needle, b'--'],
                                cwd=repo, env=environment(), stdout=stdout, stderr=stderr)
    path = output.with_suffix('.stdout')
    with path.open('rb') as stream:
        matches = sum(bool(re.fullmatch(rb'commit [0-9a-f]{40}\n', line)) for line in stream)
    return dict(status=result.returncode, stdout_bytes=path.stat().st_size,
                stdout_sha256=digest(path), stderr_sha256=digest(output.with_suffix('.stderr')),
                matches=matches)


def freeze(repo, candidates_path, destination):
    candidates = json.loads(candidates_path.read_text())
    for candidate in candidates:
        needle = bytes.fromhex(candidate['hex'])
        if not needle or b'\0' in needle:
            raise ValueError('needles require nonempty bytes without NUL')
        if not re.fullmatch(r'[a-z0-9-]+', candidate['id']):
            raise ValueError('unsafe needle id')
        if candidate['id'].endswith('-reproduced'):
            raise ValueError('needle ID uses reserved reproduction suffix')
    roles = [c['role'] for c in candidates]
    expected = ['common'] * 2 + ['rare'] * 2 + ['zero-match'] * 2 + [
        'single-byte', 'two-byte', 'long', 'spaces', 'unicode', 'newline']
    if sorted(roles) != sorted(expected) or len({c['id'] for c in candidates}) != 12:
        raise ValueError('twelve unique IDs and the approved workload roles are required')
    for c in candidates:
        needle = bytes.fromhex(c['hex'])
        role = c['role']
        if ((role == 'single-byte' and len(needle) != 1) or
                (role == 'two-byte' and len(needle) != 2) or
                (role == 'long' and len(needle) < 80) or
                (role == 'spaces' and b' ' not in needle) or
                (role == 'newline' and b'\n' not in needle) or
                (role == 'unicode' and not any(ord(ch) > 127 for ch in needle.decode('utf-8')))):
            raise ValueError('needle does not meet its declared role: ' + c['id'])
    shape = inspect(repo)
    destination.mkdir()  # Never overwrite previously frozen evidence.
    manifest = dict(schema=1, qualification=False, shape=shape, needles=[],
                    git_path=GIT, git_sha256=digest(GIT),
                    git_build=git(repo, 'version', '--build-options').decode(),
                    environment={k: v for k, v in environment().items()
                                 if k.startswith('GIT_') or k in ['PATH', 'LC_ALL', 'TZ']},
                    source_sha256=digest(__file__), candidates_sha256=digest(candidates_path))
    for candidate in candidates:
        print('freeze', repo, candidate['id'], flush=True)
        record = reference(repo, bytes.fromhex(candidate['hex']), destination / candidate['id'])
        print(record, flush=True)
        manifest['needles'].append(dict(candidate, **record))
        save(destination / 'manifest.partial.json', manifest)
        if record['status']:
            raise ValueError('reference failed; partial attempt retained')
        if candidate['role'] == 'zero-match' and record['matches']:
            raise ValueError('zero-match candidate selected commits; replace and retain this attempt')
    common = [c['matches'] for c in manifest['needles'] if c['role'] == 'common']
    rare = [c['matches'] for c in manifest['needles'] if c['role'] == 'rare']
    if not min(rare) > 0 or not min(common) > max(rare):
        raise ValueError('common/rare candidates unsuitable; replace and retain this attempt')
    # Re-run exactly the reference search; compare every byte outside any timing interval.
    for candidate in manifest['needles']:
        output = destination / (candidate['id'] + '-reproduced')
        result = reference(repo, bytes.fromhex(candidate['hex']), output)
        if result != {k: candidate[k] for k in result}:
            raise ValueError('reference output did not reproduce: ' + candidate['id'])
        for suffix in ['.stdout', '.stderr']:
            if not filecmp.cmp((destination / candidate['id']).with_suffix(suffix),
                               output.with_suffix(suffix), shallow=False):
                raise ValueError('reference bytes did not reproduce: ' + candidate['id'])
    if inspect(repo) != shape:
        raise ValueError('repository changed during freeze')
    save(destination / 'manifest.json', manifest)
    print('frozen and reproduced', destination, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('inspect')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--name', choices=PINS, required=True)
    p = commands.add_parser('freeze')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'inspect':
        save(args.output, inspect(args.repo))
    elif args.command == 'prepare':
        prepare(args.root, args.name)
    else:
        freeze(args.repo.resolve(), args.candidates, args.output_dir)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
