"""Rank option probabilities and conservatively gate automated decisions."""
import math

from .backend import Backend, LocalLayaBackend, ReviewNeeded
from .config import LayaSettings
from .models import LayaResult
from .questions import email_questions


def probability(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
        raise ValueError("Invalid probability")
    return float(value)


class LayaEmailClassifier:
    def __init__(self, settings: LayaSettings | None = None, backend: Backend | None = None):
        self.settings = settings or LayaSettings()
        self.backend = backend if backend is not None else LocalLayaBackend(self.settings)

    @classmethod
    def from_env(cls, env_file=".env"):
        return cls(LayaSettings.from_env(env_file))

    def classify(self, text: str) -> LayaResult:
        s = self.settings
        if not isinstance(text, str) or not text.strip():
            return LayaResult(review_reason="invalid_input", reason="Email text is empty or is not a string.")
        if len(text) > s.max_input_chars:
            return LayaResult(review_reason="input_too_long", reason="Email exceeds the character limit.")
        questions = email_questions()
        try:
            response = self.backend.predict(text, questions)
        except ReviewNeeded as exc:
            return LayaResult(review_reason=exc.code, reason=str(exc))
        except Exception:
            # Model download, device, and inference failures are review outcomes;
            # do not expose SDK exceptions that can include tokens or email text.
            return LayaResult(review_reason="model_error", reason="Local model loading or inference failed.")
        try:
            answer = response["answers"]["email_intent"]
            scores = answer["probabilities"]
            if answer["type"] != "choice" or set(scores) != set(questions["email_intent"]["criteria"]):
                raise ValueError("Unexpected labels")
            scores = {label: probability(value) for label, value in scores.items()}
            if not math.isclose(sum(scores.values()), 1, abs_tol=0.001):
                raise ValueError("Invalid probability total")
            ranked = sorted(scores, key=scores.get, reverse=True)
            winner = ranked[0]
            # SDK rounds probabilities to 4 decimals, so allow its argmax to
            # select either tied maximum; tied predictions still go to review.
            choice = answer["choice"]
            if choice not in scores or scores[choice] != scores[winner]:
                raise ValueError("Choice contradicts probabilities")
            confidence = scores[winner]
            margin = confidence - scores[ranked[1]]
            entropy = probability(answer["confidence"])
            act = probability(answer["action"]["act_probability"])
            routing = response.get("routing", {})
            tokens = response.get("usage", {}).get("input_tokens")
            if not isinstance(routing, dict) or (tokens is not None and (type(tokens) is not int or tokens < 0)):
                raise ValueError("Invalid metadata")
        except (KeyError, TypeError, ValueError, AttributeError):
            return LayaResult(review_reason="invalid_response", reason="Laya returned an invalid option-score response.")
        failures = []
        if confidence < s.min_probability:
            failures.append("low_probability")
        if margin <= 0 or margin < s.min_margin:
            failures.append("ambiguous_intent")
        if act < s.min_act_probability:
            failures.append("model_abstention")
        return LayaResult(
            category=None if failures else winner, suggested_category=winner,
            status="NEEDS_REVIEW" if failures else "CLASSIFIED", review_required=bool(failures),
            review_reason=failures[0] if failures else None,
            reason=("Human review required: " + ", ".join(failures) + ".") if failures else
                   "Highest-scoring intent passed probability, margin and action gates.",
            confidence=confidence, margin=round(margin, 6), probabilities=scores,
            entropy_confidence=entropy, act_probability=act, routing=routing, input_tokens=tokens)
