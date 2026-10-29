#!/usr/bin/env python3
"""Frozen, local source-history workloads. Development tooling, not product indexing."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import filecmp
import hashlib
import heapq
import json
import math
import os
import re
import signal
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time

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


def selected_environment():
    return {k: v for k, v in environment().items()
            if k.startswith('GIT_') or k in ['PATH', 'LC_ALL', 'TZ', 'HOME', 'XDG_CONFIG_HOME']}


def git(repo, *args, **kwargs):
    return subprocess.run([GIT, '-C', str(repo), *args], env=environment(),
                          check=True, stdout=subprocess.PIPE, **kwargs).stdout


def digest(path, check_cancelled=None):
    result = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            if check_cancelled is not None:
                check_cancelled()
            result.update(chunk)
    return result.hexdigest()


def save(path, value):
    path = Path(path)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix=path.name + '.', delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(json.dumps(value, indent=2, sort_keys=True) + '\n')
        os.replace(temporary, path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()


def attribute_inputs(repo, common):
    system_path = os.fsdecode(git(repo, '-c', 'pickaxe.auditpath=%(prefix)/etc/gitattributes',
                                 'config', '--path', '--get', 'pickaxe.auditpath').strip())
    configured = subprocess.run([GIT, '-C', str(repo), 'config', '--path', '--get', 'core.attributesFile'],
                                env=environment(), capture_output=True)
    if configured.returncode not in (0, 1):
        raise ValueError('cannot inspect configured attribute file')
    user_path = (os.fsdecode(configured.stdout.strip()) if configured.returncode == 0 else
                 str(Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'git/attributes'))
    result = {}
    for label, name in [('user', user_path), ('system', system_path),
                        ('repository', str(common / 'info/attributes'))]:
        if label == 'user' and configured.returncode == 0 and not user_path:
            result[label] = dict(path=None, state='disabled')
            continue
        path = Path(name)
        if not path.is_absolute():
            path = repo / path
        result[label] = dict(path=str(path.resolve()), state='absent')
        if path.exists():
            result[label].update(state='present', bytes=path.stat().st_size, sha256=digest(path))
        elif path.is_symlink():
            raise ValueError('broken attribute-file symlink: ' + str(path))
    return result


def repository_state(repo):
    repo = Path(repo).resolve()
    common = Path(os.fsdecode(git(repo, 'rev-parse', '--git-common-dir').strip()))
    if not common.is_absolute():
        common = repo / common
    if ((common / 'shallow').exists() or (common / 'objects/info/alternates').exists()
            or (common / 'objects/info/http-alternates').exists()):
        raise ValueError('workload must have complete independent object storage')
    if (common / 'info/grafts').exists():
        raise ValueError('history grafts are forbidden')
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
    objects = common / 'objects'
    storage = []
    for path in sorted(objects.rglob('*')):
        if path.is_symlink():
            raise ValueError('symlink in workload object storage')
        if path.is_file():
            storage.append(dict(path=path.relative_to(objects).as_posix(),
                                bytes=path.stat().st_size, sha256=digest(path)))
    packs = [dict(name=Path(record['path']).name, bytes=record['bytes'], sha256=record['sha256'])
             for record in storage if record['path'].startswith('pack/') and record['path'].endswith('.pack')]
    return dict(state_schema=1, head=head, refs=refs, symbolic_head='refs/heads/benchmark', worktrees=worktrees,
                packs=packs, packed_object_bytes=sum(p['bytes'] for p in packs), storage=storage,
                count_objects=git(repo, 'count-objects', '-v').decode(), config_hex=config.hex(),
                attributes=attribute_inputs(repo, common),
                home=os.environ.get('HOME'), xdg_config_home=os.environ.get('XDG_CONFIG_HOME'))


def validate_shape(repo, shape):
    state = repository_state(repo)
    metrics = {'commits', 'merges', 'root_commits', 'parent_edges', 'max_parents',
               'reachable_objects', 'reachable_bytes', 'unique_blobs', 'unique_blob_bytes',
               'largest_blobs', 'total_objects', 'out_of_scope_objects'}
    if not metrics <= shape.keys():
        raise ValueError('cached shape has missing characterization fields')
    legacy = 'storage' not in shape and 'state_schema' not in shape
    permitted_omissions = {'storage', 'state_schema', 'attributes', 'home', 'xdg_config_home'} if legacy else set()
    if not (state.keys() - permitted_omissions) <= shape.keys():
        raise ValueError('cached shape has missing repository inputs')
    if not legacy and shape['state_schema'] != 1:
        raise ValueError('unsupported cached repository state schema')
    if legacy:
        # Upgrade this session's older, fully packed reports without walking history.
        # Exact pack bytes bind their object contents; no unrecorded loose/auxiliary
        # objects are accepted. Subsequent checks also bind indexes and metadata.
        expected_files = {f"pack/{pack['name']}" for pack in shape['packs']}
        expected_files |= {str(Path(name).with_suffix('.idx')) for name in expected_files}
        if ('count: 0\n' not in shape['count_objects'] or
                {record['path'] for record in state['storage']} != expected_files):
            raise ValueError('legacy shape requires a full inspection of changed object storage')
    for key, value in state.items():
        if key in shape and shape[key] != value:
            raise ValueError('repository differs from recorded shape: ' + key)
    return dict(shape, **state)


def inspect(repo, shape_manifest=None):
    if shape_manifest is not None:
        raw = shape_manifest.read_bytes()
        saved = json.loads(raw)
        result = validate_shape(repo, saved.get('shape', saved))
        result['characterization_source'] = dict(
            method='reused characterization; graph metrics not recomputed',
            manifest_path=str(shape_manifest.resolve()), manifest_sha256=hashlib.sha256(raw).hexdigest())
        return result
    repo = Path(repo).resolve()
    state = repository_state(repo)
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
    if repository_state(repo) != state:
        raise ValueError('repository changed during characterization')
    return dict(commits=commits, merges=merges, root_commits=roots, parent_edges=parent_edges,
                max_parents=max_parents, reachable_objects=counts, reachable_bytes=sizes,
                unique_blobs=counts.get('blob', 0), unique_blob_bytes=sizes.get('blob', 0),
                largest_blobs=[list(item) for item in sorted(largest, reverse=True)], total_objects=total,
                out_of_scope_objects=total - sum(counts.values()),
                characterization_source=dict(method='full history enumeration', tool_sha256=digest(__file__)),
                **state)


def prepare(root, name):
    root = root.resolve()
    source = root / 'sources' / (name + '.git')
    url, a, b = PINS[name]
    # The network acquisition is explicit and can be resumed before preparation.
    if not source.exists():
        raise ValueError(f'first: git init --bare {source}; git -C {source} fetch --no-tags {url} {b}')
    git(source, 'fsck', '--full', '--no-reflogs')
    acquisition_path = source / 'acquisition.json'
    acquisition = (json.loads(acquisition_path.read_text()) if acquisition_path.exists() else
                   dict(source_url=url, transport='git fetch --no-tags URL PIN'))
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
            source_url=acquisition['source_url'], acquisition=acquisition, pinned_commit=oid,
            preparation='complete B fetch; private object copy; checkout A/B; no repack',
            shape=shape))
        print(name, label, shape['commits'], shape['unique_blob_bytes'], flush=True)


class CaptureInterrupted(InterruptedError):
    def __init__(self, error, result):
        super().__init__(str(error))
        self.result = result


class CaptureProcesses:
    """Own process creation, waiting and group cleanup for captured commands."""
    def __init__(self):
        self.lock = threading.Lock()
        self.active = set()
        self.cancelled = False

    def run(self, *args, **kwargs):
        process = None
        started = time.perf_counter_ns()
        main_thread = threading.current_thread() is threading.main_thread()
        try:
            pending, handlers = [], {}
            try:
                # Python dispatches signals on the main thread. Worker launches
                # instead synchronize registration with cancellation via the lock.
                if main_thread:
                    for signum in [signal.SIGALRM, signal.SIGTERM]:
                        handlers[signum] = signal.signal(signum, lambda sig, frame: pending.append((sig, frame)))
                with self.lock:
                    self.check_cancelled()
                    process = subprocess.Popen(*args, start_new_session=True, **kwargs)
                    self.active.add(process)
            finally:
                for signum, handler in handlers.items():
                    signal.signal(signum, handler)
            if pending:
                signum, frame = pending[0]
                handler = handlers[signum]
                if callable(handler):
                    handler(signum, frame)
                elif handler != signal.SIG_IGN:
                    raise InterruptedError('capture interrupted by signal ' + str(signum))
            status = process.wait()
            finished = time.perf_counter_ns()
        except BaseException as error:
            self.cancel()
            if process is not None:
                process.wait()
            raise CaptureInterrupted(error, dict(
                status=process.returncode if process is not None else None,
                started_ns=started, finished_ns=time.perf_counter_ns())) from error
        finally:
            if process is not None:
                with self.lock:
                    self.active.discard(process)
        return dict(status=status, started_ns=started, finished_ns=finished)

    def check_cancelled(self):
        if self.cancelled:
            raise InterruptedError('capture cancelled; raw streams retained')

    @staticmethod
    def _signal_group(process, signum):
        process.poll()
        try:
            os.killpg(process.pid, signum)
        except ProcessLookupError:
            pass
        except PermissionError as error:
            # macOS can report EPERM for an exited but unreaped leader. Reap
            # before retrying its saved group ID, which may still contain helpers.
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                raise error
            try:
                os.killpg(process.pid, signum)
            except ProcessLookupError:
                pass

    def cancel(self):
        if threading.current_thread() is threading.main_thread():
            signal.setitimer(signal.ITIMER_REAL, 0)
        with self.lock:
            if self.cancelled:
                return
            self.cancelled = True
            processes = list(self.active)
            if not processes:
                return
            for process in processes:
                self._signal_group(process, signal.SIGTERM)
            # A group can outlive its leader. Give all groups one common grace
            # interval, then kill surviving members independently of parent status.
            time.sleep(0.5)
            for process in processes:
                self._signal_group(process, signal.SIGKILL)
            for process in processes:
                process.wait()


def capture_record(output, status, processes=None):
    path = output.with_suffix('.stdout')
    check = processes.check_cancelled if processes is not None else None
    matches = 0
    with path.open('rb') as stream:
        for line in stream:
            if check is not None:
                check()
            matches += bool(re.fullmatch(rb'commit [0-9a-f]{40}\n', line))
    return dict(status=status, stdout_bytes=path.stat().st_size,
                stdout_sha256=digest(path, check), stderr_sha256=digest(output.with_suffix('.stderr'), check),
                matches=matches)


def reference(repo, needle, output, processes=None):
    processes = processes or CaptureProcesses()
    with output.with_suffix('.stdout').open('wb') as stdout, output.with_suffix('.stderr').open('wb') as stderr:
        result = processes.run([os.fsencode(GIT), b'--no-pager', b'log', b'--all', b'-S' + needle, b'--'],
                               cwd=repo, env=environment(), stdout=stdout, stderr=stderr)
    if processes.cancelled:
        raise InterruptedError("capture cancelled; raw streams retained")
    return capture_record(output, result['status'], processes)


def capture_batch(repo, candidates, destination, jobs, completed, suffix=''):
    processes = CaptureProcesses()
    with ThreadPoolExecutor(max_workers=jobs) as executor:
        futures = {}
        try:
            for candidate in candidates:
                future = executor.submit(reference, repo, bytes.fromhex(candidate['hex']),
                                         destination / (candidate['id'] + suffix), processes)
                futures[future] = candidate
            for future in as_completed(futures):
                completed(futures[future], future.result())
        except BaseException:
            processes.cancel()
            for future in futures:
                future.cancel()
            raise


def compare_record(expected, actual, original, reproduced, *, compare_stderr=True):
    if not compare_stderr:
        actual = {key: value for key, value in actual.items() if not key.startswith("stderr_")}
    if actual != {key: expected[key] for key in actual}:
        raise ValueError('reference output did not reproduce: ' + str(original))
    for suffix in (['.stdout', '.stderr'] if compare_stderr else ['.stdout']):
        if not filecmp.cmp(original.with_suffix(suffix), reproduced.with_suffix(suffix), shallow=False):
            raise ValueError('reference bytes did not reproduce: ' + str(original))


def validate_match_role(record):
    if record['role'] == 'zero-match' and record['matches']:
        raise ValueError('zero-match candidate selected commits; replace and retain this attempt')


def freeze(repo, candidates_path, destination, shape_manifest=None, jobs=1, resume=False,
           preflight=False, budget=None):
    if jobs < 1:
        raise ValueError('jobs must be positive')
    if resume and shape_manifest is not None:
        raise ValueError('resume uses the retained checkpoint shape; omit --shape-manifest')
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
    if not preflight and budget is None:
        raise ValueError('execution requires an approved --budget-seconds; use --preflight first')
    previous = None
    if resume:
        if (destination / 'manifest.json').exists():
            raise ValueError('freeze already completed; use reproduce instead')
        previous_raw = (destination / 'manifest.partial.json').read_bytes()
        previous = json.loads(previous_raw)
        shape = validate_shape(repo, previous['shape'])
    else:
        if shape_manifest is None:
            raise ValueError('freeze requires --shape-manifest; characterize separately')
        shape = inspect(repo, shape_manifest)
        if destination.exists():
            raise ValueError("destination already exists")
    manifest = dict(schema=1, qualification=False, shape=shape, needles=[],
                    git_path=GIT, git_sha256=digest(GIT),
                    git_build=git(repo, 'version', '--build-options').decode(),
                    environment=selected_environment(),
                    source_sha256=digest(__file__), candidates_sha256=digest(candidates_path),
                    jobs=jobs, approved_budget_seconds=budget,
                    method='untimed reference preparation', reproduced=[])
    originals, reproduced = {}, set()
    if previous is not None:
        for key in ['schema', 'git_path', 'git_sha256', 'git_build', 'environment', 'candidates_sha256']:
            if manifest[key] != previous[key]:
                raise ValueError('checkpoint input changed: ' + key)
        definitions = {candidate['id']: candidate for candidate in candidates}
        for record in previous['needles']:
            name = record['id']
            if name not in definitions or name in originals or record['status'] != 0:
                raise ValueError('checkpoint has unknown/duplicate/unsuccessful query')
            if any(record[key] != value for key, value in definitions[name].items()):
                raise ValueError('checkpoint needle changed')
            actual = capture_record(destination / name, record['status'])
            if actual != {key: record[key] for key in actual}:
                raise ValueError('checkpoint capture changed: ' + name)
            validate_match_role(record)
            originals[name] = record
        for name in previous.get('reproduced', []):
            if name not in originals or name in reproduced:
                raise ValueError('checkpoint reproduction has no unique original')
            output = destination / (name + '-reproduced')
            compare_record(originals[name], capture_record(output, 0), destination / name, output)
            reproduced.add(name)

    if preflight:
        print_plan(repo, candidates, destination, originals, reproduced, jobs)
        return
    if previous is None:
        destination.mkdir()  # Never overwrite previously frozen evidence.
    else:
        backup = Path(tempfile.mkdtemp(prefix='resume-', dir=destination))
        (backup / 'manifest.partial.json').write_bytes(previous_raw)
        for candidate in candidates:
            name = candidate['id']
            pending = ([name] if name not in originals else [])
            pending += ([name + '-reproduced'] if name not in reproduced else [])
            for base in pending:
                for extension in ['.stdout', '.stderr']:
                    path = (destination / base).with_suffix(extension)
                    if path.exists():
                        path.rename(backup / path.name)
        manifest['resumed_from'] = previous.get('resumed_from', []) + [dict(
            directory=backup.name, manifest_sha256=hashlib.sha256(previous_raw).hexdigest(),
            source_sha256=previous['source_sha256'], reused_originals=sorted(originals),
            reused_reproductions=sorted(reproduced))]

    def checkpoint():
        manifest['needles'] = [originals[c['id']] for c in candidates if c['id'] in originals]
        manifest['reproduced'] = [c['id'] for c in candidates if c['id'] in reproduced]
        save(destination / 'manifest.partial.json', manifest)

    def original_completed(candidate, record):
        print('captured', candidate['id'], record, flush=True)
        originals[candidate['id']] = dict(candidate, **record)
        checkpoint()
        if record['status']:
            raise ValueError('reference failed; partial attempt retained')
        validate_match_role(originals[candidate['id']])

    checkpoint()
    capture_batch(repo, [c for c in candidates if c['id'] not in originals],
                  destination, jobs, original_completed)
    common = [c['matches'] for c in manifest['needles'] if c['role'] == 'common']
    rare = [c['matches'] for c in manifest['needles'] if c['role'] == 'rare']
    if not min(rare) > 0 or not min(common) > max(rare):
        raise ValueError('common/rare candidates unsuitable; replace and retain this attempt')
    # Re-run exactly the reference search; compare every byte outside any timing interval.
    def reproduction_completed(candidate, result):
        output = destination / (candidate['id'] + '-reproduced')
        compare_record(originals[candidate['id']], result, destination / candidate['id'], output)
        reproduced.add(candidate['id'])
        checkpoint()
        print('reproduced', candidate['id'], flush=True)

    capture_batch(repo, [c for c in candidates if c['id'] not in reproduced],
                  destination, jobs, reproduction_completed, suffix='-reproduced')
    for candidate in manifest['needles']:
        validate_match_role(candidate)
        original = destination / candidate['id']
        actual = capture_record(original, candidate['status'])
        if actual != {key: candidate[key] for key in actual}:
            raise ValueError('retained original changed: ' + candidate['id'])
        output = destination / (candidate['id'] + '-reproduced')
        compare_record(candidate, capture_record(output, 0), original, output)
    validate_shape(repo, shape)
    if digest(__file__) != manifest['source_sha256']:
        raise ValueError('tool source changed during freeze')
    save(destination / 'manifest.json', manifest)
    print('frozen and reproduced', destination, flush=True)


def print_plan(repo, candidates, destination, originals, reproduced, jobs, reproduction_only=False, observation_directory=None):
    commands = []
    observed = []
    for name in originals:
        stream = ((observation_directory or destination) / name).with_suffix('.stdout')
        stat = stream.stat()
        observed.append(dict(id=name, stdout_bytes=stat.st_size,
            approximate_write_interval_seconds=max(0, stat.st_mtime - getattr(stat, 'st_birthtime', stat.st_mtime))))
    phases = [('', {})] if reproduction_only else [('', originals), ('-reproduced', reproduced)]
    for suffix, completed in phases:
        for candidate in candidates:
            name = candidate['id']
            if name in completed:
                continue
            commands.append(dict(cwd=str(repo), needle_hex=candidate['hex'],
                argv=[GIT, '--no-pager', 'log', '--all',
                      '-S' + os.fsdecode(bytes.fromhex(candidate['hex'])), '--'],
                stdout=str((destination / (name + suffix)).with_suffix('.stdout')),
                stderr=str((destination / (name + suffix)).with_suffix('.stderr'))))
    print(json.dumps(dict(commands=commands, jobs=jobs, observed=observed,
        cache='identity validated; no graph enumeration',
        output_policy='full raw streams; checkpoint completed queries; archive interrupted files on resume',
        cost_note='Write intervals are retrospective observations, not latency samples or estimates. Remaining query costs are unknown.'), indent=2), flush=True)


def reproduce(repo, frozen, destination, preflight=False, budget=None):
    if not preflight and budget is None:
        raise ValueError('execution requires an approved --budget-seconds; use --preflight first')
    manifest_path = frozen / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    source_hash, manifest_hash = digest(__file__), digest(manifest_path)
    profile = selected_environment()
    if any(profile.get(key) != value for key, value in manifest['environment'].items()):
        raise ValueError('environment differs from frozen inputs')
    shape = validate_shape(repo, manifest['shape'])
    if manifest['git_path'] != GIT or manifest['git_sha256'] != digest(GIT):
        raise ValueError('Git differs from frozen executable')
    for candidate in manifest['needles']:
        if not re.fullmatch(r'[a-z0-9-]+', candidate['id']):
            raise ValueError('unsafe needle id')
        actual = capture_record(frozen / candidate['id'], candidate['status'])
        if candidate['status'] != 0 or actual != {key: candidate[key] for key in actual}:
            raise ValueError('reference bytes did not reproduce: retained capture changed')
    if preflight:
        print_plan(repo, manifest['needles'], destination,
                   {c['id']: c for c in manifest['needles']}, set(), 1,
                   reproduction_only=True, observation_directory=frozen)
        return
    destination.mkdir()
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for candidate in manifest['needles']:
        print('reproduce', repo, candidate['id'], flush=True)
        result = reference(repo, bytes.fromhex(candidate['hex']), destination / candidate['id'])
        compare_record(candidate, result, frozen / candidate['id'], destination / candidate['id'])
    validate_shape(repo, shape)
    if digest(__file__) != source_hash or digest(manifest_path) != manifest_hash:
        raise ValueError('tool source or frozen manifest changed during reproduction')
    save(destination / 'verified.json', dict(
        frozen_manifest_sha256=manifest_hash, source_sha256=source_hash, environment=profile,
        started_at=started, completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        shape=shape, byte_comparisons=len(manifest['needles']) * 2,
        note='Dependencies observed for this reproduction interval, not retroactively for original capture.'))
    print('audited byte reproduction complete', destination, flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    p = commands.add_parser('inspect', aliases=['validate'])
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--shape-manifest', type=Path,
                   help='reuse prior characterization after checking all object-file hashes and repository inputs')
    p = commands.add_parser('characterize', help='explicit full history enumeration')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p = commands.add_parser('prepare')
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--name', choices=PINS, required=True)
    p = commands.add_parser('freeze')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--candidates', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--shape-manifest', type=Path,
                   help='reuse the prepared shape instead of repeating full history characterization')
    p.add_argument('--jobs', type=int, default=1, help='parallel readers for untimed query preparation only')
    p.add_argument('--resume', action='store_true', help='verify and reuse a retained partial freeze')
    p = commands.add_parser('reproduce')
    p.add_argument('--repo', type=Path, required=True)
    p.add_argument('--frozen', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    for name in ('characterize', 'prepare', 'freeze', 'reproduce'):
        commands.choices[name].add_argument('--budget-seconds', type=float,
            help='approved wall-clock execution limit, including validation and final checks')
    for name in ('freeze', 'reproduce'):
        commands.choices[name].add_argument('--preflight', action='store_true',
            help='validate inputs and print remaining commands without running queries or writing files')
    args = parser.parse_args()
    budget = getattr(args, 'budget_seconds', None)
    if budget is not None:
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError('budget must be finite and positive')
        signal.signal(signal.SIGALRM, exhausted_budget)
        signal.setitimer(signal.ITIMER_REAL, budget)
    if args.command in ('prepare', 'characterize') and budget is None:
        raise ValueError('full history execution requires an approved --budget-seconds')
    if args.command in ('inspect', 'validate'):
        if args.shape_manifest is None:
            raise ValueError('validation requires --shape-manifest; use characterize for a full history walk')
        save(args.output, inspect(args.repo, args.shape_manifest))
    elif args.command == 'characterize':
        save(args.output, inspect(args.repo))
    elif args.command == 'prepare':
        prepare(args.root, args.name)
    elif args.command == 'freeze':
        freeze(args.repo.resolve(), args.candidates, args.output_dir, args.shape_manifest,
               args.jobs, args.resume, args.preflight, budget)
    else:
        reproduce(args.repo.resolve(), args.frozen, args.output_dir, args.preflight, budget)


class RuntimeBudgetExpired(RuntimeError):
    pass


def exhausted_budget(signum, frame):
    raise RuntimeBudgetExpired("runtime budget exhausted; completion pending; partial evidence retained")


def terminate_preparation(signum, frame):
    raise InterruptedError('benchmark preparation interrupted by SIGTERM')


if __name__ == '__main__':
    previous_sigterm = signal.signal(signal.SIGTERM, terminate_preparation)
    try:
        try:
            main()
        except (OSError, ValueError, subprocess.CalledProcessError, RuntimeBudgetExpired) as error:
            sys.exit(str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGTERM, previous_sigterm)
