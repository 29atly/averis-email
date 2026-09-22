import unittest
from unittest.mock import patch
from averis_email.classifier import ClassificationDecision, classify_email
from averis_email.orchestrator import run_pipeline
from averis_email.schemas import PipelineResult
from averis_email.ui_api import to_case

class ReviewCategoryTests(unittest.TestCase):
    email = {'email_id': 'test', 'subject': 'Lunch', 'body': 'Want to meet for lunch?', 'attachments': []}

    def test_accepted_general_finishes_without_review(self):
        with patch('averis_email.orchestrator.classify_email', return_value=ClassificationDecision('GENERAL')):
            result = run_pipeline(None, self.email)
        self.assertEqual(result.category, 'GENERAL')
        self.assertFalse(result.review_required)
        self.assertIsNone(result.status)

    def test_unresolved_public_classifier_returns_review(self):
        with patch('averis_email.classifier.get_classifier_mode') as mode, patch('averis_email.classifier.get_classifier') as factory:
            mode.return_value.value = 'cascade'
            factory.return_value.return_value = ClassificationDecision(None, True, {'category': None})
            result = classify_email(self.email)
        self.assertEqual(result.category, 'REVIEW')
        self.assertTrue(result.review_required)
        self.assertIsNone(result.details['category'])

    def test_failure_and_abstention_require_review(self):
        for failure in [ClassificationDecision('REVIEW', True), RuntimeError('unavailable')]:
            kwargs = {'side_effect': failure} if isinstance(failure, Exception) else {'return_value': failure}
            with self.subTest(failure=str(failure)), patch('averis_email.orchestrator.classify_email', **kwargs):
                result = run_pipeline(None, self.email)
            self.assertEqual(result.category, 'REVIEW')
            self.assertTrue(result.model_dump()['review_required'])
            self.assertEqual(result.review_context.stage, 'classification')

    def test_missing_documents_keep_comparison_category(self):
        with patch('averis_email.orchestrator.classify_email', return_value=ClassificationDecision('BL_COMPARISON')):
            result = run_pipeline(None, self.email)
        self.assertEqual(result.category, 'BL_COMPARISON')
        self.assertTrue(result.review_required)

    def test_legacy_unresolved_ui_and_submission_compatibility(self):
        result = PipelineResult(email_id='test', category='GENERAL', status='NEEDS_REVIEW', diff_detail={'classification': {'reason': 'Uncertain'}})
        state = {'result': result.model_dump(), 'duration': 0, 'revision': 1, 'activity': []}
        self.assertEqual(to_case(self.email, state).category, 'review')
        result.category = 'REVIEW'
        self.assertEqual(result.to_submission_entry()['category'], 'GENERAL')
        self.assertEqual(result.to_submission_entry()['status'], 'NEEDS_REVIEW')
