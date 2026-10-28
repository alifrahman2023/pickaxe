#!/usr/bin/env python3
"""Run macOS development checks and collect source-pinned evidence (stdlib only)."""
import argparse
import ast
import gzip
import hashlib
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SUITES = {'cli_baseline': 'tests/cli_baseline.py',
          'candidate_containment': 'tests/candidate_containment.py'}
MODEL_SOURCES = {'tests/candidate_containment.py', 'tests/fixtures/candidate_model.py',
                 'tests/fixtures/ordered_replay.py'}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def expected_tests(path):
    tree = ast.parse(path.read_text())
    return sorted(f'{node.name}.{method.name}' for node in tree.body
                  if isinstance(node, ast.ClassDef) for method in node.body
                  if isinstance(method, ast.FunctionDef) and method.name.startswith('test_'))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify(bundle, current_sources=False):
    require(bundle['schema'] == 1, 'unsupported evidence schema')
    require(bundle['ctest_status'] == 0, 'CTest failed')
    require(bundle['tool_test_status'] == 0, 'evidence tool self-tests failed')
    junit = ET.fromstring(bundle['junit'])
    cases = junit.findall('.//testcase')
    require(sorted(c.attrib['name'] for c in cases) == sorted(SUITES), 'missing/extra CTest entries')
    require(all(c.find('failure') is None and c.find('error') is None
                and c.find('skipped') is None for c in cases), 'failed/skipped CTest entry')
    require(not re.search(r'OK \(skipped=|\bskipped=[1-9]', bundle['ctest_log']),
            'unittest skips are not complete evidence')
    require(set(bundle['records']) == set(SUITES), 'missing/extra evidence groups')
    total = 0
    for group, records in bundle['records'].items():
        names = ['.'.join(record['test'].split('.')[-2:]) for record in records]
        require(sorted(names) == bundle['expected_tests'][group], f'{group}: incomplete/duplicate records')
        total += len(records)
        for record in records:
            if group == 'cli_baseline':
                require(record['fixture_source_sha256'] == bundle['sources'][SUITES[group]],
                        'CLI fixture source hash mismatch')
                require(record['textconv_source_sha256'] == bundle['sources']['tests/helpers/controlled_textconv.py'],
                        'textconv source hash mismatch')
                require(record['pk_executable_sha256'] == bundle['pk_sha256'], 'pk binary hash mismatch')
                git_hash = record['git_executable_sha256']
            else:
                normalized = {}
                for path, digest in record['source_sha256'].items():
                    source = Path(path)
                    if source.is_absolute():
                        source = source.relative_to(bundle['source_root'])
                    normalized[source.as_posix()] = digest
                require(MODEL_SOURCES <= normalized.keys(), 'candidate source metadata incomplete')
                for path, digest in normalized.items():
                    require(bundle['sources'][path] == digest, 'model source hash mismatch')
                git_hash = record['git_sha256']
            require(git_hash == bundle['git_sha256'], 'Git binary hash mismatch')
    counts = [int(n) for n in re.findall(r'Ran (\d+) tests? in', bundle['ctest_log'])]
    require(sorted(counts) == sorted(len(r) for r in bundle['records'].values()),
            'unittest execution counts differ from retained records')
    if current_sources:
        for path, digest in bundle['sources'].items():
            source = (ROOT / path).resolve()
            require(ROOT in source.parents, 'source path outside repository')
            require(sha256(source) == digest, f'changed source: {path}')
        require({group: expected_tests(ROOT / path) for group, path in SUITES.items()}
                == bundle['expected_tests'], 'current test inventory differs')
    return total


def execute(command, log):
    print('+ ' + ' '.join(str(arg) for arg in command), flush=True)
    result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    log.write_bytes(result.stdout)
    sys.stdout.buffer.write(result.stdout)
    sys.stdout.flush()
    return result.returncode


def run(build):
    require(sys.platform == 'darwin', 'these process/PTY development checks currently require macOS')
    build = build.resolve()
    output = build / 'evidence'
    output.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='run-', dir=output))
    print(f'Evidence attempt: {attempt}', flush=True)
    tool_status = execute([sys.executable, str(ROOT / 'tests/check_evidence.py'), '-v'],
                          attempt / 'tool-tests.log')
    require(tool_status == 0, f'evidence tool self-tests failed; see {attempt}')
    commands = [
        ['cmake', '-S', str(ROOT), '-B', str(build), '-G', 'Unix Makefiles',
         '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_COMPILER=/usr/bin/clang++',
         '-DBUILD_TESTING=ON', f'-DPICKAXE_EVIDENCE_DIR={attempt}'],
        ['cmake', '--build', str(build)],
    ]
    for label, command in zip(('configure', 'build'), commands):
        require(execute(command, attempt / (label + '.log')) == 0, f'{label} failed; see {attempt}')
    source_paths = [ROOT / 'CMakeLists.txt', ROOT / 'src/main.cpp']
    source_paths += list((ROOT / 'tests').rglob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    source_paths += list((ROOT / '.github/workflows').glob('*.yml'))
    sources = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(source_paths)}
    git = shutil.which('git')
    require(git is not None, 'Git missing on inherited PATH')
    git_hash, pk_hash = sha256(git), sha256(build / 'pk')
    status = execute(['ctest', '--test-dir', str(build), '--output-on-failure', '-V',
                      '--output-junit', str(attempt / 'ctest.xml')], attempt / 'ctest.log')
    require(status == 0, f'CTest failed; partial evidence retained at {attempt}')
    bundle = dict(schema=1, qualification=False, source_root=str(ROOT),
                  revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  worktree_status=subprocess.check_output(['git', 'status', '--short'], cwd=ROOT).decode(),
                  platform=platform.platform(), python=platform.python_version(),
                  git_path=git, git_sha256=git_hash, pk_sha256=pk_hash, sources=sources,
                  git_build=subprocess.check_output([git, 'version', '--build-options']).decode(),
                  configure_log=(attempt / 'configure.log').read_text(),
                  build_log=(attempt / 'build.log').read_text(),
                  tool_test_status=tool_status, tool_test_log=(attempt / 'tool-tests.log').read_text(),
                  ctest_status=status, ctest_log=(attempt / 'ctest.log').read_text(),
                  junit=(attempt / 'ctest.xml').read_text(),
                  expected_tests={group: expected_tests(ROOT / path) for group, path in SUITES.items()},
                  records={group: [json.loads(p.read_text()) for p in sorted((attempt / group.replace('_', '-')).glob('*.json'))]
                           for group in SUITES})
    total = verify(bundle, current_sources=True)
    destination = attempt / 'checks.json.gz'
    raw = json.dumps(bundle, indent=2).encode() + b'\n'
    destination.write_bytes(gzip.compress(raw, mtime=0))
    require(gzip.decompress(destination.read_bytes()) == raw, 'archive round-trip failed')
    # Keep each attempt; latest is updated only after all validation succeeds.
    shutil.copyfile(destination, output / 'latest.json.gz')
    print(f'Verified {total} checks: {destination}\nLatest: {output / "latest.json.gz"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    run_parser = sub.add_parser('run', help='configure, build, run full suite and package fresh evidence')
    run_parser.add_argument('--build-dir', type=Path, default=ROOT / 'build/checks')
    check_parser = sub.add_parser('verify', help='validate a checks.json.gz bundle; historical sources allowed by default')
    check_parser.add_argument('archive', type=Path)
    check_parser.add_argument('--current-sources', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'run':
            run(args.build_dir)
        else:
            bundle = json.loads(gzip.decompress(args.archive.read_bytes()))
            print(f'Verified {verify(bundle, args.current_sources)} retained checks')
    except (OSError, ValueError, KeyError, ET.ParseError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'check: {error}\n')


if __name__ == '__main__':
    main()
