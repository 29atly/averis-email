from typing import Literal

from pydantic import BaseModel, Field

from averis_email.llm_classifier.models import Category


class LayaResult(BaseModel):
    category: Category | None = None
    suggested_category: Category | None = None
    status: Literal["CLASSIFIED", "NEEDS_REVIEW"] = "NEEDS_REVIEW"
    review_required: bool = True
    review_reason: str | None = None
    reason: str
    # Winning probability, NOT Laya's entropy-based confidence field.
    confidence: float | None = None
    margin: float | None = None
    probabilities: dict[str, float] = Field(default_factory=dict)
    entropy_confidence: float | None = None
    act_probability: float | None = None
    routing: dict = Field(default_factory=dict)
    input_tokens: int | None = None
