import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from averis_email.classifier import ClassificationDecision, CLASSIFIER_FACTORIES, classify_email, get_classifier
from averis_email.config.classification import CLASSIFIER_MODES, ClassifierMode, get_classifier_mode
from averis_email.llm_classifier.models import ClassificationResult
from averis_email.laya_classifier.models import LayaResult
from averis_email.orchestrator import run_pipeline


class SelectionTests(unittest.TestCase):
    def setUp(self):
        get_classifier.cache_clear()

    def tearDown(self):
        get_classifier.cache_clear()

    @patch.dict(os.environ, {}, clear=True)
    def test_default_file_environment_and_invalid_mode(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / '.env'
            self.assertEqual(get_classifier_mode(path), ClassifierMode.CASCADE)
            path.write_text('EMAIL_CLASSIFIER_MODE=laya\n')
            self.assertEqual(get_classifier_mode(path), ClassifierMode.LAYA)
            with patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'llm'}):
                self.assertEqual(get_classifier_mode(path), ClassifierMode.LLM)
            path.write_text('EMAIL_CLASSIFIER_MODE=typo\n')
            with self.assertRaisesRegex(ValueError, 'EMAIL_CLASSIFIER_MODE'):
                get_classifier_mode(path)

    def test_registry_covers_all_modes(self):
        self.assertEqual(set(CLASSIFIER_FACTORIES), set(ClassifierMode))
        self.assertEqual(set(CLASSIFIER_MODES), {'cascade', 'rule_based', 'laya', 'llm'})

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'cascade'})
    def test_cascade_rule_matches_skip_models_including_general(self):
        with patch.dict(CLASSIFIER_FACTORIES, {ClassifierMode.LAYA: Mock(), ClassifierMode.LLM: Mock()}):
            for body, expected in [('Please check draft BL.', 'BL_COMPARISON'),
                                   ('Holiday announcement', 'GENERAL')]:
                result = classify_email({'body': body})
                self.assertEqual(result.category, expected)
                self.assertEqual(result.details['backend'], 'rule_based')
            CLASSIFIER_FACTORIES[ClassifierMode.LAYA].assert_not_called()
            CLASSIFIER_FACTORIES[ClassifierMode.LLM].assert_not_called()

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'cascade'})
    def test_cascade_laya_success_skips_llm(self):
        laya = Mock(return_value=ClassificationDecision('SI_REQUEST'))
        llm_factory = Mock()
        with patch.dict(CLASSIFIER_FACTORIES, {ClassifierMode.LAYA: Mock(return_value=laya),
                                              ClassifierMode.LLM: llm_factory}):
            result = classify_email({'body': 'Help arrange the shipping paperwork.'})
        self.assertEqual(result.category, 'SI_REQUEST')
        self.assertEqual(result.details['backend'], 'laya')
        llm_factory.assert_not_called()

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'cascade'})
    def test_cascade_laya_failures_reach_llm_in_order(self):
        for failure in [ClassificationDecision(None, True, {'review_reason': 'low_probability'}),
                        ClassificationDecision('UNSUPPORTED'), RuntimeError('sensitive error')]:
            with self.subTest(failure=type(failure).__name__):
                get_classifier.cache_clear()
                calls = []
                def laya_factory(env_file):
                    calls.append('laya')
                    if isinstance(failure, Exception):
                        raise failure
                    return lambda email: failure
                def llm_factory(env_file):
                    calls.append('llm')
                    return lambda email: ClassificationDecision('SI_REQUEST')
                with patch.dict(CLASSIFIER_FACTORIES, {ClassifierMode.LAYA: laya_factory,
                                                      ClassifierMode.LLM: llm_factory}):
                    result = classify_email({'body': 'Help arrange the shipping paperwork.'})
                self.assertEqual(calls, ['laya', 'llm'])
                self.assertEqual(result.category, 'SI_REQUEST')
                self.assertEqual([a['backend'] for a in result.details['attempts']],
                                 ['rule_based', 'laya', 'llm'])
                self.assertNotIn('sensitive error', str(result.details))

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'cascade'})
    def test_cascade_exhaustion_stops_pipeline(self):
        for llm in [Mock(return_value=lambda email: ClassificationDecision(None, True,
                        {'review_reason': 'ambiguous_intent'})), Mock(side_effect=ValueError('secret'))]:
            get_classifier.cache_clear()
            with patch.dict(CLASSIFIER_FACTORIES, {
                ClassifierMode.LAYA: Mock(return_value=lambda email: ClassificationDecision(None, True)),
                ClassifierMode.LLM: llm,
            }), patch('averis_email.stages.classification.find_si_bl') as attachments:
                result = run_pipeline(None, {'email_id': 'test', 'body': 'Unclear'})
            self.assertEqual(result.status, 'NEEDS_REVIEW')
            self.assertEqual(len(result.diff_detail['classification']['attempts']), 3)
            self.assertEqual(result.review_context.original_email,
                             {'email_id': 'test', 'body': 'Unclear'})
            self.assertNotIn('secret', str(result))
            attachments.assert_not_called()

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'cascade'})
    def test_cascade_invalid_input_skips_models(self):
        with patch.dict(CLASSIFIER_FACTORIES, {ClassifierMode.LAYA: Mock(), ClassifierMode.LLM: Mock()}):
            for email in [{}, {'body': '  '}, {'subject': ['invalid']}, {'body': 123}]:
                result = classify_email(email)
                self.assertTrue(result.review_required)
                self.assertEqual(result.details['review_reason'], 'invalid_input')
            CLASSIFIER_FACTORIES[ClassifierMode.LAYA].assert_not_called()
            CLASSIFIER_FACTORIES[ClassifierMode.LLM].assert_not_called()

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'rule_based'})
    def test_rules_do_not_build_model_backends(self):
        with patch.dict(CLASSIFIER_FACTORIES, {ClassifierMode.LAYA: Mock(), ClassifierMode.LLM: Mock()}):
            result = classify_email({'body': 'Please check draft BL.'})
            self.assertEqual(result.category, 'BL_COMPARISON')
            CLASSIFIER_FACTORIES[ClassifierMode.LAYA].assert_not_called()
            CLASSIFIER_FACTORIES[ClassifierMode.LLM].assert_not_called()

    def test_text_backends_selected_cached_and_receive_email_only(self):
        cases = [
            ('llm', 'averis_email.llm_classifier.EmailClassifier.from_env',
             ClassificationResult(category='INVOICE_QUERY', status='CLASSIFIED', review_required=False,
                                  review_reason=None, reason='Invoice question.')),
            ('laya', 'averis_email.laya_classifier.LayaEmailClassifier.from_env',
             LayaResult(category='INVOICE_QUERY', status='CLASSIFIED', review_required=False, reason='Invoice question.')),
        ]
        for mode, target, result in cases:
            with self.subTest(mode=mode), patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': mode}), patch(target) as factory:
                factory.return_value.classify.return_value = result
                email = {'subject': 'Invoice', 'body': 'Please clarify.', 'attachments': ['SI.pdf']}
                self.assertEqual(classify_email(email).category, 'INVOICE_QUERY')
                classify_email(email)
                factory.assert_called_once()
                factory.return_value.classify.assert_called_with('Subject: Invoice\n\nPlease clarify.')

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'llm'})
    @patch('averis_email.llm_classifier.EmailClassifier.from_env')
    @patch('averis_email.stages.classification.find_si_bl')
    def test_review_stops_pipeline_and_preserves_details(self, attachments, factory):
        factory.return_value.classify.return_value = ClassificationResult.review('ambiguous_intent', 'Mixed requests.')
        result = run_pipeline(None, {'email_id': 'test', 'body': 'Unclear'})
        self.assertEqual(result.status, 'NEEDS_REVIEW')
        self.assertEqual(result.diff_detail['classification']['review_reason'], 'ambiguous_intent')
        self.assertIsNone(result.diff_detail['classification']['category'])
        self.assertEqual(result.diff_detail['classification']['mode'], 'llm')
        attachments.assert_not_called()

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'laya'})
    @patch('averis_email.laya_classifier.LayaEmailClassifier.from_env')
    def test_accepted_comparison_continues_to_attachment_resolution(self, factory):
        factory.return_value.classify.return_value = LayaResult(
            category='BL_COMPARISON', status='CLASSIFIED', review_required=False, reason='Clear request.')
        result = run_pipeline(None, {'email_id': 'test', 'body': 'Compare documents', 'attachments': []})
        self.assertEqual(result.category, 'BL_COMPARISON')
        self.assertEqual(result.review_reason, 'missing_attachment')

    @patch.dict(os.environ, {'EMAIL_CLASSIFIER_MODE': 'invalid'})
    def test_invalid_configuration_does_not_silently_use_rules(self):
        result = run_pipeline(None, {'email_id': 'test', 'body': 'Invoice question'})
        self.assertEqual(result.status, 'NEEDS_REVIEW')
        self.assertIn('EMAIL_CLASSIFIER_MODE', result.error)


if __name__ == '__main__':
    unittest.main()
