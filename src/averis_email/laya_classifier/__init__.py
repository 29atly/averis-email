"""Local option-scoring email classifier. Heavy dependencies load on first use."""
from .classifier import LayaEmailClassifier
from .config import LayaSettings
from .models import LayaResult

__all__ = ["LayaEmailClassifier", "LayaSettings", "LayaResult"]
