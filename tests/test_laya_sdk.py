"""Optional SDK contract checks: no weights, credentials, or network required."""
import importlib.util
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from averis_email.laya_classifier.backend import LocalLayaBackend, ReviewNeeded, check_context
from averis_email.laya_classifier.config import LayaSettings
from averis_email.laya_classifier.questions import email_questions


class WordTokenizer:
    mask_token = "[MASK]"
    mask_token_id = 1
    cls_token_id = 2
    sep_token_id = 3

    def __call__(self, text, **kwargs):
        return {"input_ids": [4] * len(text.split())}


@unittest.skipUnless(importlib.util.find_spec("laya"), "Install the optional laya extra for SDK checks")
class SdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("USE_TF", "0")
        from laya import Agent
        cls.agent_type = Agent

    def test_context_and_question_budget_checks(self):
        question = email_questions()["email_intent"]
        agent = SimpleNamespace(tok=WordTokenizer(), cfg={"max_len": 512, "head_max_len": 192},
                                _to_internal=self.agent_type._to_internal)
        check_context(agent, "Short email", question)
        with self.assertRaises(ReviewNeeded) as caught:
            check_context(agent, "word " * 512, question)
        self.assertEqual(caught.exception.code, "input_too_long")
        agent.cfg["head_max_len"] = 20
        with self.assertRaises(ReviewNeeded) as caught:
            check_context(agent, "Short email", question)
        self.assertEqual(caught.exception.code, "question_too_long")

    @patch("averis_email.laya_classifier.backend.check_context")
    @patch("huggingface_hub.snapshot_download", return_value="/tmp/model")
    @patch("laya.load")
    @patch("laya.Router")
    def test_route_load_cache_and_predict(self, router_type, load, download, context):
        router = router_type.return_value
        router.route.return_value = {"model": "multilingual", "reason": "Detected language"}
        router.loaded = []
        router.load.return_value = load.return_value
        load.return_value.predict.return_value = {"answers": {}}
        backend = LocalLayaBackend(LayaSettings())
        backend.predict("Email", email_questions())
        self.assertTrue(all(file.startswith("multilingual/") for file in download.call_args.kwargs["allow_patterns"]))
        self.assertEqual(load.call_args.kwargs["subfolder"], "multilingual")
        context.assert_called_once()
        router.loaded = ["multilingual"]
        backend.predict("Next email", email_questions())
        download.assert_called_once()
        router_type.assert_called_once()

    @patch("laya.Router")
    def test_english_override_cannot_bypass_language_gate(self, router_type):
        router = router_type.return_value
        router.route.return_value = {"model": "multilingual"}
        with self.assertRaises(ReviewNeeded) as caught:
            LocalLayaBackend(LayaSettings(checkpoint="english")).predict("非英语邮件", email_questions())
        self.assertEqual(caught.exception.code, "unsupported_language")
        router.load.assert_not_called()


if __name__ == "__main__":
    unittest.main()
