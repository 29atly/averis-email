"""Exercise real Person 2 stages through orchestration, mocking later stages.

create=True allows the team's unfinished reader/extractor functions to be mocked.
These tests check integration contracts, not document parsing or field accuracy.
"""
import unittest
from unittest.mock import call, patch
from averis_email import orchestrator as pipeline
from averis_email.schemas import AttachmentResolutionResult, ExtractedDoc


class EmailIntelligenceIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.loader = object()
        self.reader = self._mock(pipeline.ingestion, 'read_document',
            side_effect=lambda loader, path: ExtractedDoc(attachment_path=path))
        self.extractor = self._mock(pipeline.extraction, 'extract_fields', side_effect=lambda doc: doc)
        self.validator = self._mock(pipeline.validation, 'missing_fields', return_value=[])
        self.comparer = self._mock(pipeline.comparison, 'compare_fields', return_value=([], {}))

    def _mock(self, module, name, **kwargs):
        patcher = patch.object(module, name, create=True, **kwargs)
        result = patcher.start()
        self.addCleanup(patcher.stop)
        return result

    def run_email(self, paths):
        return pipeline.run_pipeline(self.loader, {
            'email_id': 'integration_case', 'body': 'Please compare the SI and draft BL.',
            'attachments': paths,
        })

    def assert_no_downstream_calls(self):
        for stage in [self.reader, self.extractor, self.validator, self.comparer]:
            stage.assert_not_called()

    def test_noncomparison_bypasses_attachment_and_reader(self):
        with patch.object(pipeline.classification, 'find_si_bl') as resolver:
            result = pipeline.run_pipeline(self.loader, {
                'email_id': 'invoice_case', 'body': 'Please clarify invoice 42.',
                'attachments': ['invoice.pdf'],
            })
        self.assertEqual(result.category, 'INVOICE_QUERY')
        resolver.assert_not_called()
        self.assert_no_downstream_calls()

    def test_missing_ambiguous_and_conflicting_attachments_stop_early(self):
        cases = [([], 'missing_attachment'),
                 (['SI.pdf', 'BL_v1.pdf', 'BL_v2.pdf'], 'missing_attachment'),
                 (['SI.pdf', 'BL_commercial_invoice.pdf'], 'wrong_doc_type')]
        for paths, reason in cases:
            with self.subTest(paths=paths):
                result = self.run_email(paths)
                self.assertEqual(result.status, 'NEEDS_REVIEW')
                self.assertEqual(result.review_reason, reason)
                self.assertTrue(result.diff_detail['attachment_warnings'])
                self.assert_no_downstream_calls()

    def test_valid_pair_preserves_paths_order_and_loader(self):
        si, bl = 'Folder/ShippingInstruction.xlsx', 'Folder/DRAFTBL.pdf'
        result = self.run_email([bl, si])
        self.assertEqual(result.status, 'OK')
        self.assertEqual(self.reader.call_args_list, [call(self.loader, si), call(self.loader, bl)])
        self.assertEqual(result.si.attachment_path, si)
        self.assertEqual(result.bl.attachment_path, bl)
        self.assertNotIn('attachment_warnings', result.diff_detail)

    def test_success_and_mismatch_preserve_warnings_and_diff(self):
        for defects, expected in [([], 'OK'), (['shipper'], 'MISMATCH')]:
            with self.subTest(status=expected):
                detail = {'shipper': {'si': 'A', 'bl': 'B'}} if defects else {'checked': True}
                self.comparer.return_value = (defects, detail)
                result = self.run_email(['SI.pdf', 'BL.pdf', 'invoice.pdf'])
                self.assertEqual(result.status, expected)
                self.assertEqual(result.has_defect, bool(defects))
                self.assertEqual(result.defect_fields, defects)
                self.assertEqual(result.diff_detail['attachment_warnings'], ['Unrecognized attachment role: invoice.pdf'])
                for key, value in detail.items():
                    self.assertEqual(result.diff_detail[key], value)
                self.assertNotIn('attachment_warnings', detail)
                self.assertNotIn('diff_detail', result.to_submission_entry())

    def test_read_and_extraction_errors_preserve_warnings(self):
        for stage in [self.reader, self.extractor]:
            with self.subTest(stage=stage):
                original = stage.side_effect
                stage.side_effect = RuntimeError('test failure')
                try:
                    result = self.run_email(['SI.pdf', 'BL.pdf', 'invoice.pdf'])
                finally:
                    stage.side_effect = original
                self.assertEqual(result.status, 'NEEDS_REVIEW')
                self.assertEqual(result.review_reason, 'unreadable')
                self.assertIn('test failure', result.error)
                self.assertTrue(result.diff_detail['attachment_warnings'])
                self.validator.assert_not_called()
                self.comparer.assert_not_called()

    def test_unreadable_document_preserves_warnings(self):
        self.reader.side_effect = lambda loader, path: ExtractedDoc(attachment_path=path, readable=False)
        result = self.run_email(['SI.pdf', 'BL.pdf', 'invoice.pdf'])
        self.assertEqual(result.review_reason, 'unreadable')
        self.assertTrue(result.diff_detail['attachment_warnings'])
        self.validator.assert_not_called()
        self.comparer.assert_not_called()

    def test_missing_values_preserve_both_details(self):
        self.validator.return_value = ['shipper']
        result = self.run_email(['SI.pdf', 'BL.pdf', 'invoice.pdf'])
        self.assertEqual(result.review_reason, 'missing_value')
        self.assertEqual(result.diff_detail['missing_fields'], ['shipper'])
        self.assertTrue(result.diff_detail['attachment_warnings'])
        self.comparer.assert_not_called()

    def test_defensive_missing_path_preserves_warnings(self):
        resolution = AttachmentResolutionResult(si_path='SI.pdf', warnings=['BL unresolved'])
        with patch.object(pipeline.classification, 'find_si_bl', return_value=resolution):
            result = self.run_email([])
        self.assertEqual(result.review_reason, 'missing_attachment')
        self.assertEqual(result.diff_detail['attachment_warnings'], ['BL unresolved'])
        self.assert_no_downstream_calls()

    def test_resolver_exception_returns_review(self):
        with patch.object(pipeline.classification, 'find_si_bl', side_effect=RuntimeError('resolution failed')):
            result = self.run_email([])
        self.assertEqual(result.status, 'NEEDS_REVIEW')
        self.assertEqual(result.review_reason, 'unreadable')
        self.assertIn('resolution failed', result.error)
        self.assert_no_downstream_calls()


if __name__ == '__main__':
    unittest.main()
