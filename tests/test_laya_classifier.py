"""Offline scoring/gate tests, independent of large model downloads."""
import math
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from averis_email.laya_classifier import LayaEmailClassifier, LayaSettings
from averis_email.laya_classifier.backend import ReviewNeeded
from averis_email.laya_classifier.evaluate import summarize
from averis_email.laya_classifier.questions import email_questions


def response(scores=None, act=0.9):
    scores = scores or dict(zip(email_questions()["email_intent"]["criteria"], [.9, .025, .025, .025, .025]))
    return {"answers": {"email_intent": {"type": "choice", "choice": max(scores, key=scores.get),
             "probabilities": scores, "confidence": .71, "action": {"act_probability": act}}},
            "usage": {"input_tokens": 100}, "routing": {"model": "english"}}


class LayaTests(unittest.TestCase):
    def classify(self, raw, settings=None):
        return LayaEmailClassifier(settings, Mock(predict=Mock(return_value=raw))).classify("Please check the draft BL.")

    def test_each_category_uses_highest_probability(self):
        for label in email_questions()["email_intent"]["criteria"]:
            scores = {key: .9 if key == label else .025 for key in email_questions()["email_intent"]["criteria"]}
            result = self.classify(response(scores))
            self.assertEqual(result.category, label)
            self.assertFalse(result.review_required)
            self.assertEqual(result.confidence, .9)
            self.assertEqual(result.entropy_confidence, .71)
            self.assertEqual(result.probabilities, scores)

    def test_probability_margin_and_action_gates(self):
        labels = list(email_questions()["email_intent"]["criteria"])
        for probabilities, act, expected in [
            ([.6, .1, .1, .1, .1], .9, "low_probability"),
            ([.45, .4, .05, .05, .05], .9, "ambiguous_intent"),
            ([.9, .025, .025, .025, .025], .1, "model_abstention")]:
            settings = LayaSettings(min_probability=.4 if expected == "ambiguous_intent" else .8)
            result = self.classify(response(dict(zip(labels, probabilities)), act), settings)
            self.assertEqual(result.review_reason, expected)
            self.assertIsNone(result.category)
            self.assertEqual(result.suggested_category, labels[0])

    def test_exact_tie_always_review_even_with_zero_thresholds(self):
        labels = list(email_questions()["email_intent"]["criteria"])
        raw = response(dict(zip(labels, [.5, .5, 0, 0, 0])))
        raw["answers"]["email_intent"]["choice"] = labels[1]
        result = self.classify(raw, LayaSettings(min_probability=0, min_margin=0, min_act_probability=0))
        self.assertEqual(result.review_reason, "ambiguous_intent")

    def test_bad_scores_or_inconsistent_choice_never_classify(self):
        cases = [{}, {"answers": []}]
        for value in [float("nan"), float("inf"), -.1, 1.1, True, "0.9", None]:
            raw = response()
            raw["answers"]["email_intent"]["probabilities"]["BL_COMPARISON"] = value
            cases.append(raw)
        for field, value in [("choice", "SPAM"), ("probabilities", {"OTHER": 1}), ("action", {}),
                             ("confidence", math.nan), ("type", "score")]:
            raw = response()
            raw["answers"]["email_intent"][field] = value
            cases.append(raw)
        raw = response()
        raw["answers"]["email_intent"]["probabilities"]["BL_COMPARISON"] = .8
        cases.append(raw)
        for raw in cases:
            with self.subTest(raw=raw):
                self.assertEqual(self.classify(raw).review_reason, "invalid_response")

    def test_empty_or_oversize_input_does_not_load_model(self):
        backend = Mock()
        classifier = LayaEmailClassifier(LayaSettings(max_input_chars=10), backend)
        for text in [None, "", "  ", 12, "x" * 11]:
            self.assertTrue(classifier.classify(text).review_required)
        backend.predict.assert_not_called()

    def test_backend_review_and_exception(self):
        for exception, expected in [(ReviewNeeded("input_too_long", "Too long"), "input_too_long"),
                                    (RuntimeError("secret"), "model_error")]:
            result = LayaEmailClassifier(backend=Mock(predict=Mock(side_effect=exception))).classify("Email")
            self.assertEqual(result.review_reason, expected)
            self.assertNotIn("secret", result.model_dump_json())

    def test_questions_have_independent_copies(self):
        changed = email_questions()
        changed["email_intent"]["criteria"].clear()
        self.assertEqual(len(email_questions()["email_intent"]["criteria"]), 5)

    @patch.dict(os.environ, {}, clear=True)
    def test_settings_precedence_and_threshold_validation(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text("LAYA_MIN_PROBABILITY=0.9\nHF_TOKEN=secret\n")
            self.assertEqual(LayaSettings.from_env(path).min_probability, .9)
            with patch.dict(os.environ, {"LAYA_MIN_PROBABILITY": ".7"}):
                settings = LayaSettings.from_env(path)
                self.assertEqual(settings.min_probability, .7)
                self.assertNotIn("secret", repr(settings))
        for value in [-1, 1.01, math.nan, math.inf]:
            with self.assertRaises(ValueError):
                LayaSettings(min_probability=value)

    def test_evaluation_denominators(self):
        accepted = self.classify(response()).model_dump()
        reviewed = self.classify(response(act=.1)).model_dump()
        invalid = LayaEmailClassifier().classify("").model_dump()
        summary = summarize([{"expected": "BL_COMPARISON", "result": accepted},
                             {"expected": "SPAM", "result": reviewed},
                             {"expected": "GENERAL", "result": invalid}])
        self.assertEqual(summary["coverage"], 1 / 3)
        self.assertEqual(summary["accepted_accuracy"], 1)
        self.assertEqual(summary["top_choice_accuracy_on_scored"], .5)
        self.assertIsNone(summarize([])["accepted_accuracy"])


if __name__ == "__main__":
    unittest.main()
