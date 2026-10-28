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
            schema=1, ctest_status=0, tool_test_status=0,
            junit='<testsuite><testcase name="cli_baseline"/><testcase name="candidate_containment"/></testsuite>',
            ctest_log='Ran 1 test in 0.1s\nOK\nRan 1 test in 0.1s\nOK\n',
            expected_tests={group: ['Fixture.test_example'] for group in CHECK.SUITES},
            sources={path: 'original' for path in [*CHECK.SUITES.values(), 'tests/helpers/controlled_textconv.py',
                                                                 'tests/fixtures/candidate_model.py',
                                                                 'tests/fixtures/ordered_replay.py']},
            source_root='/historical/checkout', git_sha256='git', pk_sha256='pk',
            records={
                'cli_baseline': [dict(test='__main__.Fixture.test_example',
                                      fixture_source_sha256='original', textconv_source_sha256='original',
                                      git_executable_sha256='git', pk_executable_sha256='pk')],
                'candidate_containment': [dict(test='__main__.Fixture.test_example', git_sha256='git',
                                              source_sha256={'tests/candidate_containment.py': 'original',
                                                             'tests/fixtures/candidate_model.py': 'original',
                                                             'tests/fixtures/ordered_replay.py': 'original'})]})

    def test_historical_bundle_does_not_require_current_checkout_hashes(self):
        self.assertEqual(CHECK.verify(self.bundle), 2)
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

    def test_failed_run_is_rejected_even_with_complete_records(self):
        self.bundle['ctest_status'] = 1
        with self.assertRaisesRegex(ValueError, 'CTest failed'):
            CHECK.verify(self.bundle)

    def test_skipped_checks_are_rejected(self):
        self.bundle['ctest_log'] = 'Ran 1 test in 0.1s\nOK (skipped=1)'
        with self.assertRaisesRegex(ValueError, 'skips'):
            CHECK.verify(self.bundle)


if __name__ == '__main__':
    unittest.main()
