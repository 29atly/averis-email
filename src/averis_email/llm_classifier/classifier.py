"""Provider-independent validation and human-review routing."""
import json

from pydantic import ValidationError

from .config import Settings
from .models import ClassificationResult, ModelDecision
from .prompt import SYSTEM_PROMPT
from .providers import InvalidResponse, Provider, ProviderError, make_provider


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate response key")
        result[key] = value
    return result


class EmailClassifier:
    def __init__(self, provider: Provider, max_input_chars: int = 50000):
        self.provider = provider
        self.max_input_chars = max_input_chars

    @classmethod
    def from_env(cls, provider: str | None = None, env_file=".env"):
        settings = Settings.from_env(provider, env_file)
        return cls(make_provider(settings), settings.max_input_chars)

    def classify(self, text: str) -> ClassificationResult:
        if not isinstance(text, str) or not text.strip():
            return ClassificationResult.review("invalid_input", "Email text is empty or is not a string.")
        if len(text) > self.max_input_chars:
            return ClassificationResult.review("invalid_input", "Email exceeds the input limit; review without truncating context.")
        try:
            raw = self.provider.complete(SYSTEM_PROMPT, text, ModelDecision.model_json_schema())
            parsed = json.loads(raw, object_pairs_hook=_unique_keys)
            decision = ModelDecision.model_validate(parsed)
            if not decision.reason.strip():
                raise ValueError("Empty reason")
        except ProviderError:
            return ClassificationResult.review("provider_error", "Classification provider unavailable or request rejected.")
        except (InvalidResponse, ValidationError, ValueError, TypeError):
            return ClassificationResult.review("invalid_response", "Model response failed the output gate; human review required.")
        if decision.decision == "NEEDS_REVIEW":
            return ClassificationResult.review("ambiguous_intent", decision.reason)
        return ClassificationResult(category=decision.decision, status="CLASSIFIED",
                                    review_required=False, review_reason=None, reason=decision.reason)
