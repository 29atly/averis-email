"""Verify the synthetic rules -> Laya fallback using the actual classifier router.

Default (offline, mocked Laya inference):
    python -m unittest discover -s tests -p "test_synthetic_fallback.py" -v

Real local-model demonstration (requires the laya optional dependencies and
checkpoint; the first inference may download it), in PowerShell:
    $env:RUN_LAYA_INTEGRATION = "1"
    python -m unittest discover -s tests -p "test_synthetic_fallback.py" -v
    Remove-Item Env:RUN_LAYA_INTEGRATION

Offline tests prove routing, not model accuracy. The opt-in test requires real
Laya to accept BL_COMPARISON at the configured thresholds. Abstention, a wrong
category, or model errors fail that demonstration; LLM cannot rescue it.
The demonstration email was selected after trying two synthetic phrasings with
real Laya. It demonstrates routing for one known example, not unseen accuracy.
The original JSON fixture is retained unchanged as an unmatched-rule example.
Attachment reading and Shanghai/Ningbo comparison belong to downstream tests.
"""
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch

from averis_email.classifier import classify_email, get_classifier
from averis_email.laya_classifier import LayaEmailClassifier
from averis_email.laya_classifier.models import LayaResult
from averis_email.stages.classification import match_email_rules


SYNTHETIC_EMAIL = Path(__file__).parent / "synthetic" / "inbox" / "synthetic_email_999.json"


class SyntheticFallbackTests(unittest.TestCase):
    def setUp(self):
        self.original_email = json.loads(SYNTHETIC_EMAIL.read_text(encoding="utf-8"))
        # Selected demonstration: natural comparison wording outside today's
        # regex patterns. Real Laya accepted this at the existing 0.80 threshold.
        # Keep the source fixture and production rules/configuration unchanged.
        self.email = {
            **self.original_email,
            "subject": "Shipping document reconciliation",
            "body": (
                "Please compare both attached shipping documents and highlight every "
                "mismatch between the carrier draft and our original instructions. "
                "Do the ports, consignee and cargo weights agree?"
            ),
        }
        get_classifier.cache_clear()
        self.addCleanup(get_classifier.cache_clear)
        # Exercise the public router irrespective of the developer's .env mode.
        mode = patch.dict(os.environ, {"EMAIL_CLASSIFIER_MODE": "cascade"})
        mode.start()
        self.addCleanup(mode.stop)

    def assert_laya_accepted(self, result):
        self.assertFalse(result.review_required, result.details)
        self.assertEqual(result.category, "BL_COMPARISON", result.details)
        self.assertEqual(result.details["mode"], "cascade")
        self.assertEqual(result.details["backend"], "laya", result.details)
        attempts = result.details["attempts"]
        self.assertEqual([a["backend"] for a in attempts], ["rule_based", "laya"])
        self.assertIsNone(attempts[0]["category"])
        self.assertTrue(attempts[0]["review_required"])
        self.assertEqual(attempts[1]["category"], "BL_COMPARISON")
        self.assertFalse(attempts[1]["review_required"])

    def test_original_email_still_has_no_rule_match(self):
        self.assertIsNone(match_email_rules(self.original_email))

    def test_synthetic_email_has_no_rule_match(self):
        # None is the real fallback trigger, not a made-up confidence score.
        self.assertIsNone(match_email_rules(self.email))

    def test_unmatched_email_calls_laya_and_skips_llm(self):
        self.assertIsNone(match_email_rules(self.email))
        accepted = LayaResult(
            category="BL_COMPARISON", status="CLASSIFIED", review_required=False,
            reason="Controlled response for the offline routing test.",
        )
        with patch.object(LayaEmailClassifier, "from_env") as factory, \
                patch("averis_email.llm_classifier.EmailClassifier.from_env") as llm:
            factory.return_value.classify.return_value = accepted
            result = classify_email(self.email)
            factory.assert_called_once_with(".env")
            factory.return_value.classify.assert_called_once_with(
                f"Subject: {self.email['subject']}\n\n{self.email['body']}"
            )
            llm.assert_not_called()
        self.assert_laya_accepted(result)

    def test_rule_matched_email_skips_both_models(self):
        email = {**self.email, "subject": "Draft BL review",
                 "body": "Please check the draft BL against the SI."}
        self.assertEqual(match_email_rules(email), "BL_COMPARISON")
        with patch.object(LayaEmailClassifier, "from_env") as laya, \
                patch("averis_email.llm_classifier.EmailClassifier.from_env") as llm:
            result = classify_email(email)
            laya.assert_not_called()
            llm.assert_not_called()
        self.assertEqual(result.category, "BL_COMPARISON")
        self.assertFalse(result.review_required)
        self.assertEqual(result.details["backend"], "rule_based")
        self.assertEqual(result.details["attempts"], [
            {"backend": "rule_based", "category": "BL_COMPARISON", "review_required": False}
        ])

    @unittest.skipUnless(os.environ.get("RUN_LAYA_INTEGRATION") == "1",
                         "Set RUN_LAYA_INTEGRATION=1 to test real local Laya inference")
    def test_real_laya_accepts_synthetic_email_without_llm(self):
        self.assertIsNone(match_email_rules(self.email))
        model = LayaEmailClassifier.from_env(".env")
        # The spy delegates to real inference; no prediction is supplied by the test.
        spy = Mock(wraps=model.classify)
        with patch.object(model, "classify", spy), \
                patch.object(LayaEmailClassifier, "from_env", return_value=model) as factory, \
                patch("averis_email.llm_classifier.EmailClassifier.from_env",
                      side_effect=AssertionError("LLM must not rescue this demonstration")) as llm:
            result = classify_email(self.email)
            factory.assert_called_once_with(".env")
            spy.assert_called_once_with(
                f"Subject: {self.email['subject']}\n\n{self.email['body']}"
            )
        print("\nReal synthetic fallback result: " + json.dumps(result.details, sort_keys=True))
        self.assert_laya_accepted(result)
        llm.assert_not_called()


if __name__ == "__main__":
    unittest.main()
