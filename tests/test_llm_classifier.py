"""Offline contract tests; no secrets or live provider calls required."""
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

from averis_email.llm_classifier import EmailClassifier, Settings
from averis_email.llm_classifier.cli import main
from averis_email.llm_classifier.models import ModelDecision
from averis_email.llm_classifier.prompt import SYSTEM_PROMPT
from averis_email.llm_classifier.providers import make_provider, post_json, ProviderError
from averis_email.schemas import CATEGORIES


def wire(decision="GENERAL", reason="Informational update."):
    return json.dumps({"decision": decision, "reason": reason})


class ClassificationTests(unittest.TestCase):
    def test_all_categories_and_abstention(self):
        for label in [*CATEGORIES, "NEEDS_REVIEW"]:
            with self.subTest(label=label):
                result = EmailClassifier(Mock(complete=Mock(return_value=wire(label)))).classify("Email")
                self.assertEqual(result.review_required, label == "NEEDS_REVIEW")
                self.assertEqual(result.category, None if result.review_required else label)
                if result.review_required:
                    self.assertEqual(result.review_reason, "ambiguous_intent")

    def test_gate_rejects_invalid_output(self):
        for raw in [wire("OTHER"), wire(reason=" "), wire(reason="x" * 501),
                    '{"decision":"GENERAL","reason":12}', '{}', '[]', 'null',
                    '```json\n' + wire() + '\n```', wire() + ' trailing',
                    '{"decision":"GENERAL","reason":"ok","extra":true}',
                    '{"decision":"GENERAL","decision":"SPAM","reason":"ok"}']:
            with self.subTest(raw=raw):
                result = EmailClassifier(Mock(complete=Mock(return_value=raw))).classify("Email")
                self.assertEqual(result.review_reason, "invalid_response")
                self.assertIsNone(result.category)

    def test_invalid_input_never_calls_provider(self):
        provider = Mock()
        for text in [None, "", "   ", 123, "a" * 11]:
            self.assertEqual(EmailClassifier(provider, 10).classify(text).review_reason, "invalid_input")
        provider.complete.assert_not_called()

    def test_provider_failure_is_review_without_error_leak(self):
        result = EmailClassifier(Mock(complete=Mock(side_effect=ProviderError("secret")))).classify("Email")
        self.assertEqual(result.review_reason, "provider_error")
        self.assertNotIn("secret", result.model_dump_json())


class ProviderTests(unittest.TestCase):
    def settings(self, name):
        return Settings(provider=name, model="test-model", api_key="test-secret",
                        base_url="https://example.test/v1", timeout=7)

    @patch("averis_email.llm_classifier.providers.post_json")
    def test_requests_share_prompt_and_schema(self, post):
        schema = ModelDecision.model_json_schema()
        for name in ["nvidia", "huggingface", "gemini"]:
            with self.subTest(provider=name):
                post.return_value = ({"candidates": [{"finishReason": "STOP", "content": {
                    "parts": [{"text": wire()}]}}]} if name == "gemini" else {
                    "choices": [{"finish_reason": "stop", "message": {"content": wire()}}]})
                result = EmailClassifier(make_provider(self.settings(name))).classify("Email body")
                self.assertEqual(result.category, "GENERAL")
                url, headers, payload, timeout = post.call_args.args
                self.assertEqual(timeout, 7)
                self.assertNotIn("test-secret", url)
                if name == "gemini":
                    self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], SYSTEM_PROMPT)
                    self.assertEqual(payload["contents"][0]["parts"][0]["text"], "Email body")
                    self.assertEqual(payload["generationConfig"]["responseJsonSchema"], schema)
                    self.assertEqual(headers["x-goog-api-key"], "test-secret")
                else:
                    self.assertEqual(payload["messages"], [{"role": "system", "content": SYSTEM_PROMPT},
                                                         {"role": "user", "content": "Email body"}])
                    self.assertEqual(headers["Authorization"], "Bearer test-secret")
                    self.assertEqual(payload["guided_json"] if name == "nvidia" else
                                     payload["response_format"]["json_schema"]["schema"], schema)

    @patch("averis_email.llm_classifier.providers.post_json")
    def test_blocked_truncated_or_missing_responses(self, post):
        for name, responses in [
            ("nvidia", [{}, {"choices": []}, {"choices": [{"finish_reason": "length",
                "message": {"content": wire()}}]}, {"choices": [{"finish_reason": "stop",
                "message": {"content": wire(), "refusal": "blocked"}}]}]),
            ("gemini", [{"promptFeedback": {"blockReason": "SAFETY"}}, {"candidates": [
                {"finishReason": "MAX_TOKENS", "content": {"parts": [{"text": wire()}]}}]}])]:
            for response in responses:
                post.return_value = response
                self.assertEqual(EmailClassifier(make_provider(self.settings(name))).classify("Email").review_reason,
                                 "invalid_response")

    @patch("averis_email.llm_classifier.providers.urlopen")
    def test_http_and_network_errors(self, opener):
        for error in [HTTPError("https://example.test", 429, "secret", {}, None), URLError("secret"), TimeoutError()]:
            opener.side_effect = error
            with self.assertRaises(ProviderError) as caught:
                post_json("https://example.test", {}, {}, 1)
            self.assertNotIn("secret", str(caught.exception))


class ConfigurationAndCliTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    def test_dotenv_and_environment_precedence(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / ".env"
            path.write_text('EMAIL_LLM_PROVIDER=gemini\nGEMINI_API_KEY="file-secret"\nGEMINI_MODEL=test\n')
            self.assertEqual(Settings.from_env(env_file=path).api_key.get_secret_value(), "file-secret")
            with patch.dict(os.environ, {"GEMINI_API_KEY": "env-secret"}):
                settings = Settings.from_env(env_file=path)
                self.assertEqual(settings.api_key.get_secret_value(), "env-secret")
                self.assertNotIn("env-secret", repr(settings))
            with self.assertRaises(ValueError):
                Settings.from_env("huggingface", path)

    @patch("averis_email.llm_classifier.cli.EmailClassifier.from_env")
    def test_cli_inbox_json_and_review_output(self, factory):
        factory.return_value = EmailClassifier(Mock(complete=Mock(return_value=wire("NEEDS_REVIEW", "Ambiguous."))))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "email.json"
            path.write_text(json.dumps({"subject": "Request", "body": "Please handle this.", "attachments": ["SI.pdf"]}))
            with patch("sys.argv", ["classify", str(path), "--provider", "gemini"]), patch("sys.stdout", new_callable=io.StringIO) as output:
                main()
            self.assertEqual(json.loads(output.getvalue())["status"], "NEEDS_REVIEW")
            self.assertEqual(factory.return_value.provider.complete.call_args.args[1],
                             "Subject: Request\n\nPlease handle this.")


if __name__ == "__main__":
    unittest.main()
