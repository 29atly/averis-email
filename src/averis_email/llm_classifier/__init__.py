"""LLM classification, usable directly or through EMAIL_CLASSIFIER_MODE=llm."""
from .classifier import EmailClassifier
from .config import Settings
from .models import ClassificationResult

__all__ = ["EmailClassifier", "Settings", "ClassificationResult"]
