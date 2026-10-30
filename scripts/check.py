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
          'candidate_containment': 'tests/candidate_containment.py',
          'publication_protocol': 'tests/publication_protocol.py'}
MODEL_SOURCES = {'tests/candidate_containment.py', 'tests/fixtures/candidate_model.py',
                 'tests/fixtures/ordered_replay.py'}
PUBLICATION_SOURCES = {'tests/publication_protocol.py', 'tests/helpers/publication_probe.cpp'}
TOOL_TEST_SOURCE = 'tests/check_evidence.py'


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


def verify_tool_tests(status, log, expected):
    require(status == 0, 'evidence tool self-tests failed')
    require(isinstance(expected, list) and expected and all(isinstance(n, str) for n in expected)
            and len(set(expected)) == len(expected), 'self-test inventory missing/empty/duplicate')
    require(not re.search(r'\bskipped=[1-9]\d*', log), 'evidence tool self-tests skipped')
    counts = [int(n) for n in re.findall(r'Ran (\d+) tests? in', log)]
    require(counts == [len(expected)], 'self-test execution count differs from declared inventory')
    require(re.search(r'^OK\s*$', log, re.MULTILINE), 'self-tests have no successful completion summary')


def verify(bundle, current_sources=False):
    require(bundle['schema'] == 2, 'unsupported evidence schema')
    require(bundle['ctest_status'] == 0, 'CTest failed')
    verify_tool_tests(bundle['tool_test_status'], bundle['tool_test_log'],
                      bundle.get('expected_tool_tests'))
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
                required = PUBLICATION_SOURCES if group == 'publication_protocol' else MODEL_SOURCES
                require(required <= normalized.keys(), f'{group}: source metadata incomplete')
                for path, digest in normalized.items():
                    require(bundle['sources'][path] == digest, 'model source hash mismatch')
                git_hash = record['git_sha256']
                if group == 'publication_protocol':
                    require(record['probe_sha256'] == bundle['publication_probe_sha256'],
                            'publication probe binary hash mismatch')
            require(git_hash == bundle['git_sha256'], 'Git binary hash mismatch')
    counts = [int(n) for n in re.findall(r'Ran (\d+) tests? in', bundle['ctest_log'])]
    require(sorted(counts) == sorted(len(r) for r in bundle['records'].values()),
            'unittest execution counts differ from retained records')
    if current_sources:
        for path, digest in bundle['sources'].items():
            source = (ROOT / path).resolve()
            require(ROOT in source.parents, 'source path outside repository')
            require(sha256(source) == digest, f'changed source: {path}')
        require(expected_tests(ROOT / TOOL_TEST_SOURCE) == bundle['expected_tool_tests'],
                'current self-test inventory differs')
        require({group: expected_tests(ROOT / path) for group, path in SUITES.items()}
                == bundle['expected_tests'], 'current test inventory differs')
    return total


def execute(command, log):
    print('+ ' + ' '.join(str(arg) for arg in command), flush=True)
    with log.open('wb') as output, subprocess.Popen(
            command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT) as process:
        try:
            while True:
                chunk = process.stdout.read1(65536)
                if not chunk:
                    break
                output.write(chunk)
                output.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            return process.wait()
        except BaseException:
            process.kill()
            process.wait()
            raise


def source_hashes():
    source_paths = [ROOT / 'CMakeLists.txt', ROOT / 'src/main.cpp']
    source_paths += list((ROOT / 'tests').rglob('*.py')) + list((ROOT / 'scripts').glob('*.py'))
    source_paths += list((ROOT / 'tests').rglob('*.cpp'))
    source_paths += list((ROOT / '.github/workflows').glob('*.yml'))
    sources = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(source_paths)}
    return sources


def unchanged_sources(sources):
    current = source_hashes()
    for path in sorted(sources.keys() | current.keys()):
        require(current.get(path) == sources.get(path), f"changed source: {path}")


def run(build):
    require(sys.platform == 'darwin', 'these process/PTY development checks currently require macOS')
    build = build.resolve()
    output = build / 'evidence'
    output.mkdir(parents=True, exist_ok=True)
    attempt = Path(tempfile.mkdtemp(prefix='run-', dir=output))
    print(f'Evidence attempt: {attempt}', flush=True)
    sources = source_hashes()
    tool_inventory = expected_tests(ROOT / TOOL_TEST_SOURCE)
    tool_status = execute([sys.executable, str(ROOT / TOOL_TEST_SOURCE), '-v'],
                          attempt / 'tool-tests.log')
    tool_log = (attempt / 'tool-tests.log').read_text()
    verify_tool_tests(tool_status, tool_log, tool_inventory)
    unchanged_sources(sources)
    commands = [
        ['cmake', '-S', str(ROOT), '-B', str(build), '-G', 'Unix Makefiles',
         '-DCMAKE_BUILD_TYPE=Release', '-DCMAKE_CXX_COMPILER=/usr/bin/clang++',
         '-DBUILD_TESTING=ON', f'-DPICKAXE_EVIDENCE_DIR={attempt}'],
        ['cmake', '--build', str(build)],
    ]
    for label, command in zip(('configure', 'build'), commands):
        require(execute(command, attempt / (label + '.log')) == 0, f'{label} failed; see {attempt}')
    git = shutil.which('git')
    require(git is not None, 'Git missing on inherited PATH')
    git_hash, pk_hash = sha256(git), sha256(build / 'pk')
    status = execute(['ctest', '--test-dir', str(build), '--output-on-failure', '-V',
                      '--output-junit', str(attempt / 'ctest.xml')], attempt / 'ctest.log')
    require(status == 0, f'CTest failed; partial evidence retained at {attempt}')
    bundle = dict(schema=2, qualification=False, source_root=str(ROOT),
                  revision=subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT).decode().strip(),
                  worktree_status=subprocess.check_output(['git', 'status', '--short'], cwd=ROOT).decode(),
                  platform=platform.platform(), python=platform.python_version(),
                  git_path=git, git_sha256=git_hash, pk_sha256=pk_hash, sources=sources,
                  publication_probe_sha256=sha256(build / 'publication_probe'),
                  git_build=subprocess.check_output([git, 'version', '--build-options']).decode(),
                  configure_log=(attempt / 'configure.log').read_text(),
                  build_log=(attempt / 'build.log').read_text(),
                  tool_test_status=tool_status, tool_test_log=tool_log, expected_tool_tests=tool_inventory,
                  ctest_status=status, ctest_log=(attempt / 'ctest.log').read_text(),
                  junit=(attempt / 'ctest.xml').read_text(),
                  expected_tests={group: expected_tests(ROOT / path) for group, path in SUITES.items()},
                  records={group: [json.loads(p.read_text()) for p in sorted((attempt / group.replace('_', '-')).glob('*.json'))]
                           for group in SUITES})
    unchanged_sources(sources)
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
