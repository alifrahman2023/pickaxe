"""Evidence validator contract: incomplete or inconsistent runs cannot pass."""
import importlib.util
from pathlib import Path
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


if __name__ == '__main__':
    unittest.main()
