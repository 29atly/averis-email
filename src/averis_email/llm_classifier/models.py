"""Shared wire schema and validated application result."""
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

Category = Literal["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
Decision = Literal["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM", "NEEDS_REVIEW"]


class ModelDecision(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    decision: Decision
    reason: str = Field(min_length=1, max_length=500)


class ClassificationResult(BaseModel):
    category: Category | None
    status: Literal["CLASSIFIED", "NEEDS_REVIEW"]
    review_required: bool
    review_reason: Literal["ambiguous_intent", "invalid_input", "invalid_response", "provider_error"] | None
    reason: str

    @classmethod
    def review(cls, code, reason):
        return cls(category=None, status="NEEDS_REVIEW", review_required=True,
                   review_reason=code, reason=reason)
