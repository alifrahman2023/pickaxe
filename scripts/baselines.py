#!/usr/bin/env python3
"""Sequential reference-Git baselines for an explicitly selected frozen workload."""
import argparse
import datetime
import json
import math
import os
import platform
import statistics
import time
from pathlib import Path
import re
import signal
import subprocess
import sys

import benchmarks as workloads


def inputs(selection_path):
    selection = json.loads(selection_path.read_text())
    original = selection['original_manifest']
    audit = selection['audited_reproduction']
    for item in [original, audit]:
        if workloads.digest(item['path']) != item['sha256']:
            raise ValueError('selected manifest identity changed')
    manifest = json.loads(Path(original['path']).read_text())
    verified = json.loads(Path(audit['path']).read_text())
    if verified['frozen_manifest_sha256'] != original['sha256']:
        raise ValueError('audited reproduction belongs to another manifest')
    if manifest['git_path'] != workloads.GIT or manifest['git_sha256'] != workloads.digest(workloads.GIT):
        raise ValueError('selected Git executable changed')
    repo = Path(selection['repo']).resolve()
    shape = workloads.validate_shape(repo, manifest['shape'])
    definitions = {c['id']: c for c in manifest['needles']}
    names = set()
    if not selection['needles']:
        raise ValueError('empty selection')
    for record in selection['needles']:
        name = record['id']
        needle = bytes.fromhex(record['hex'])
        if not re.fullmatch(r'[a-z0-9-]+', name) or name in names or not needle or b'\0' in needle:
            raise ValueError('invalid or duplicate selected needle')
        names.add(name)
        expected = definitions[name]
        if any(record[k] != v for k, v in expected.items()) or record['status'] != 0:
            raise ValueError('selection differs from frozen query')
        base = Path(original['path']).parent / name
        if Path(record['original_base']).resolve() != base.resolve():
            raise ValueError('original capture path differs from manifest')
        actual = workloads.capture_record(base, 0)
        if actual != {k: record[k] for k in actual}:
            raise ValueError('retained original capture changed')
        workloads.compare_record(record, workloads.capture_record(Path(record['reproduction_base']), 0),
                                 base, Path(record['reproduction_base']))
    return selection, repo, shape


def plan(selection, repo, destination, pickaxe=None):
    commands = []
    for record in selection['needles']:
        needle = bytes.fromhex(record['hex'])
        implementations = ['git'] + (['pickaxe'] if pickaxe else [])
        for sample in range(6):
            order = implementations if sample == 0 or sample % 2 else list(reversed(implementations))
            for implementation in order:
                argv = ([workloads.GIT, '--no-pager', 'log', '--all', '-S' + os.fsdecode(needle), '--']
                        if implementation == 'git' else [str(pickaxe), 'search', os.fsdecode(needle)])
                base = destination / f"{record['id']}-{implementation}-{sample}"
                commands.append(dict(id=record['id'], implementation=implementation, sample=sample,
                    phase='warmup' if sample == 0 else 'warm', cwd=str(repo), argv=argv,
                    stdout=str(base.with_suffix('.stdout')), stderr=str(base.with_suffix('.stderr'))))
    return commands


def hardware():
    result = dict(platform=platform.platform(), machine=platform.machine(),
                  logical_cpus=os.cpu_count(), python=sys.version,
                  python_executable=sys.executable,
                  python_sha256=workloads.digest(sys.executable))
    if sys.platform == 'darwin':
        keys = ['hw.model', 'hw.memsize', 'hw.physicalcpu', 'hw.logicalcpu']
        values = subprocess.check_output(['sysctl', '-n', *keys], text=True).splitlines()
        result['sysctl'] = dict(zip(keys, values))
    else:
        result['memory_bytes'] = os.sysconf('SC_PAGE_SIZE') * os.sysconf('SC_PHYS_PAGES')
    return result


def execute(command, repo):
    owner = workloads.CaptureProcesses()
    with Path(command['stdout']).open('wb') as stdout, Path(command['stderr']).open('wb') as stderr:
        started = time.perf_counter_ns()
        process = owner.start([os.fsencode(arg) for arg in command['argv']], cwd=repo,
                              env=workloads.environment(), stdout=stdout, stderr=stderr)
        try:
            status = process.wait()
            finished = time.perf_counter_ns()
        except BaseException:
            owner.cancel()
            process.wait()
            raise
        finally:
            owner.finished(process)
    return dict(status=status, started_ns=started, finished_ns=finished,
                elapsed_seconds=(finished - started) / 1e9 if command['phase'] == 'warm' else None)


def measure(args, selection, repo, shape, commands, source_hashes):
    destination = args.output_dir
    destination.mkdir()  # Retain every attempt; never overwrite one.
    report = dict(schema=1, qualification=False, complete=False, runs=[], summary=[],
        selection_path=str(args.selection.resolve()), selection_sha256=source_hashes[str(args.selection)],
        source_sha256=source_hashes, shape=shape, hardware=hardware(),
        selected_needles=selection['needles'], original_full_protocol_complete=False,
        load_average_before=list(os.getloadavg()),
        git_path=workloads.GIT, git_sha256=workloads.digest(workloads.GIT),
        git_build=workloads.git(repo, 'version', '--build-options').decode(),
        git_exec_path=workloads.git(repo, '--exec-path').decode().strip(),
        pickaxe=(dict(path=str(args.pickaxe.resolve()), sha256=workloads.digest(args.pickaxe))
                 if args.pickaxe else None),
        environment=workloads.selected_environment(), activity_note=args.activity_note,
        approved_budget_seconds=args.budget_seconds,
        started_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        output_sink='separate regular files for stdout and stderr, opened before each command',
        cache_policy='one unreported warm-up per query/implementation, then five warm samples; '
                     'input validation hashes packs and warms caches; no independent reset performed',
        cold=dict(status='unavailable', reason='no credible independent cache reset configured; new processes are not cold cache'),
        indexing_memory_budget='not applicable: reference searches; optional Pickaxe has no index builder here',
        method='Sequential complete processes, perf_counter_ns before Popen through wait; '
               'includes startup, Git traversal/helpers, formatting and captured output. '
               'Hashing/counting/byte comparison and metadata collection occur outside measured intervals. '
               'Popen/wait scheduling overhead is included, not subtracted. '
               'Pair order alternates by sample when --pickaxe is present. '
               'Five samples support median/range only; no tail, speedup or qualification claims.')
    expected = {c['id']: c for c in selection['needles']}
    partial = destination / 'manifest.partial.json'
    workloads.save(partial, report)
    try:
        for command in commands:
            report['current_command'] = command
            workloads.save(partial, report)
            timing = execute(command, repo)
            base = Path(command['stdout']).with_suffix('')
            record = dict(command, **workloads.capture_record(base, timing['status']),
                          **{k: v for k, v in timing.items() if k != 'status'}, bytes_verified=False)
            report['runs'].append(record)
            workloads.save(partial, report)
            workloads.compare_record(expected[command['id']],
                {k: record[k] for k in ['status', 'stdout_bytes', 'stdout_sha256', 'stderr_sha256', 'matches']},
                Path(expected[command['id']]['original_base']), base)
            record['bytes_verified'] = True
            report.pop('current_command')
            workloads.save(partial, report)
            print(f"{command['id']} {command['implementation']} {command['phase']} {command['sample']} verified", flush=True)
        for candidate in selection['needles']:
            for implementation in sorted({r['implementation'] for r in report['runs']}):
                values = [r['elapsed_seconds'] for r in report['runs'] if r['id'] == candidate['id']
                          and r['implementation'] == implementation and r['phase'] == 'warm']
                if len(values) != 5 or not all(math.isfinite(v) and v > 0 for v in values):
                    raise ValueError('incomplete/invalid warm sample set')
                report['summary'].append(dict(id=candidate['id'], implementation=implementation,
                    samples=5, values_seconds=values, median_seconds=statistics.median(values),
                    min_seconds=min(values), max_seconds=max(values)))
        for record in report['runs']:
            base = Path(record['stdout']).with_suffix('')
            actual = workloads.capture_record(base, record['status'])
            if actual != {k: record[k] for k in actual}:
                raise ValueError('retained measured capture changed: ' + str(base))
            workloads.compare_record(expected[record['id']], actual,
                                     Path(expected[record['id']]['original_base']), base)
        workloads.validate_shape(repo, shape)
        for path, digest in source_hashes.items():
            if workloads.digest(path) != digest:
                raise ValueError('measurement input/source changed: ' + path)
        if workloads.digest(workloads.GIT) != report['git_sha256']:
            raise ValueError('Git executable changed during measurement')
        if args.pickaxe and workloads.digest(args.pickaxe) != report['pickaxe']['sha256']:
            raise ValueError('Pickaxe executable changed during measurement')
        # Recheck retained expected streams and input identities before completion.
        inputs(args.selection)
        report.update(complete=True, load_average_after=list(os.getloadavg()), completed_at=datetime.datetime.now(datetime.timezone.utc).isoformat())
        workloads.save(destination / 'manifest.json', report)
        print('complete', destination, flush=True)
    except BaseException as error:
        report.update(error=str(error), complete=False)
        workloads.save(partial, report)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--selection', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--activity-note', required=True, help='observed relevant background/cache activity')
    parser.add_argument('--pickaxe', type=Path, help='optional executable for alternating sequential pairs')
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--budget-seconds', type=float)
    args = parser.parse_args()
    if not args.preflight and args.budget_seconds is None:
        raise ValueError('execution requires an approved --budget-seconds; use --preflight first')
    if args.budget_seconds is not None:
        if not math.isfinite(args.budget_seconds) or args.budget_seconds <= 0:
            raise ValueError('budget must be finite and positive')
        signal.signal(signal.SIGALRM, workloads.exhausted_budget)
        signal.setitimer(signal.ITIMER_REAL, args.budget_seconds)
    source_hashes = {str(p): workloads.digest(p) for p in
                     [args.selection, Path(__file__), Path(workloads.__file__)]}
    selection, repo, shape = inputs(args.selection)
    commands = plan(selection, repo, args.output_dir, args.pickaxe.resolve() if args.pickaxe else None)
    if args.preflight:
        print(json.dumps(dict(commands=commands, jobs=1, cold='unavailable: no independent cache reset',
            output_sink='separate regular stdout/stderr files; byte verification outside timing',
            observed=[{k: c[k] for k in ['id', 'matches', 'stdout_bytes']} for c in selection['needles']],
            remaining_cost=f'{len(commands)} complete searches; duration unknown'), indent=2))
        return
    measure(args, selection, repo, shape, commands, source_hashes)


if __name__ == '__main__':
    signal.signal(signal.SIGTERM, workloads.terminate_preparation)
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError, workloads.RuntimeBudgetExpired) as error:
        sys.exit(str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
