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


# Add new strategy factories here when extending ClassifierMode.
CLASSIFIER_FACTORIES: dict[ClassifierMode, Callable] = {
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
    decision.details = {**decision.details, "mode": mode.value}
    return decision
