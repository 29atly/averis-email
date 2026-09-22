"""Pipeline classifier selection. Backend imports and construction are lazy."""
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Callable

from averis_email.config.classification import ClassifierMode, get_classifier_mode
from averis_email.schemas import CATEGORIES


@dataclass
class ClassificationDecision:
    category: str | None
    review_required: bool = False
    details: dict = field(default_factory=dict)


def _email_text(email):
    subject, body = email.get("subject") or "", email.get("body") or ""
    if not isinstance(subject, str) or not isinstance(body, str):
        raise ValueError("Email subject and body must be strings")
    return f"Subject: {subject}\n\n{body}" if subject.strip() or body.strip() else ""


def _rule_based(env_file):
    from averis_email.stages.classification import classify_email
    return lambda email: ClassificationDecision(classify_email(email))


def _text_adapter(classifier):
    def classify(email):
        result = classifier.classify(_email_text(email))
        return ClassificationDecision(result.category, result.review_required, result.model_dump())
    return classify


def _laya(env_file):
    from averis_email.laya_classifier import LayaEmailClassifier
    return _text_adapter(LayaEmailClassifier.from_env(env_file))


def _llm(env_file):
    from averis_email.llm_classifier import EmailClassifier
    return _text_adapter(EmailClassifier.from_env(env_file=env_file))


def _cascade(env_file):
    from averis_email.stages.classification import match_email_rules

    def classify(email):
        try:
            text = _email_text(email)
        except ValueError:
            text = ""
        if not text.strip():
            return ClassificationDecision(None, True, {
                "category": None, "review_reason": "invalid_input",
                "reason": "Email text is empty or is not a string.",
            })

        category = match_email_rules(email)
        attempts = [{"backend": "rule_based", "category": category,
                     "review_required": category is None}]
        if category is not None:
            return ClassificationDecision(category, details={
                "backend": "rule_based", "attempts": attempts,
            })

        for mode in (ClassifierMode.LAYA, ClassifierMode.LLM):
            try:
                decision = get_classifier(mode, env_file)(email)
                if not decision.review_required and decision.category not in CATEGORIES:
                    decision = ClassificationDecision(None, True, {
                        "review_reason": "invalid_response",
                        "reason": "Classifier returned an unsupported category.",
                    })
            except Exception:
                # Construction and inference can fail. Never expose exception
                # text, which may contain credentials or email contents.
                decision = ClassificationDecision(None, True, {
                    "review_reason": "backend_error",
                    "reason": "Classifier initialization or inference failed.",
                })
            attempts.append({**decision.details, "backend": mode.value,
                             "category": decision.category,
                             "review_required": decision.review_required})
            if not decision.review_required:
                break
        decision.details = {**decision.details, "category": decision.category,
                            "backend": mode.value, "attempts": attempts}
        return decision

    return classify


# Add new strategy factories here when extending ClassifierMode.
CLASSIFIER_FACTORIES: dict[ClassifierMode, Callable] = {
    ClassifierMode.CASCADE: _cascade,
    ClassifierMode.RULE_BASED: _rule_based,
    ClassifierMode.LAYA: _laya,
    ClassifierMode.LLM: _llm,
}


@lru_cache(maxsize=None)
def get_classifier(mode: ClassifierMode, env_file=".env"):
    """Reuse model/client instances. Restart after changing backend settings."""
    return CLASSIFIER_FACTORIES[mode](env_file)


def classify_email(email: dict, env_file=".env") -> ClassificationDecision:
    mode = get_classifier_mode(env_file)
    decision = get_classifier(mode, str(env_file))(email)
    if not decision.review_required and decision.category not in CATEGORIES:
        raise ValueError("Classifier returned an unsupported category")
    if decision.review_required:
        # Preserve the backend's raw category/reason in details for diagnosis.
        decision.category = "REVIEW"
    decision.details = {**decision.details, "mode": mode.value}
    return decision
