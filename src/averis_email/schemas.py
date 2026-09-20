"""Shared data contracts for the pipeline -- now real Pydantic models.

Every stage module in `averis_email.stages` should accept/return objects
shaped like these. Using Pydantic (rather than plain dataclasses) means:
  - values get validated automatically (e.g. a wrong type raises a clear
    error immediately, instead of silently corrupting data downstream)
  - FastAPI (in web.py) can use these directly to auto-generate API docs
    and validate responses

Agree on this file with the whole team before anyone writes real stage
logic -- it's the contract everything else plugs into.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
STATUSES = ["OK", "MISMATCH", "NEEDS_REVIEW"]
REVIEW_REASONS = ["wrong_doc_type", "missing_attachment", "unreadable", "missing_value"]

FIELDS = [
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
    "container_count",
    "gross_weight_kg",
]


class FieldValue(BaseModel):
    """One extracted field, with evidence so a human reviewer can check it."""
    value: Optional[str] = None
    source_file: Optional[str] = None   # e.g. "attachments/email_004_SI.txt"
    source_page: Optional[int] = None   # page number, for pdf/docx/scan later
    raw_text: Optional[str] = None      # the raw snippet the value came from


class ExtractedDoc(BaseModel):
    """Everything pulled from one SI or BL attachment.

    `fields` is intentionally typed loosely (dict[str, Any]) because stage 2
    (ingestion) temporarily stores raw text under "_raw" before stage 3
    (extraction) replaces it with real FieldValue entries keyed by the names
    in FIELDS.
    """
    attachment_path: str
    doc_type: Optional[str] = None      # "SI" | "BL" | None if undetermined
    fields: dict[str, Any] = Field(default_factory=dict)
    readable: bool = True
    error: Optional[str] = None


class PipelineResult(BaseModel):
    email_id: str
    category: str
    status: Optional[str] = None
    review_reason: Optional[str] = None
    has_defect: bool = False
    defect_fields: list[str] = Field(default_factory=list)

    si: Optional[ExtractedDoc] = None
    bl: Optional[ExtractedDoc] = None
    diff_detail: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None

    def to_submission_entry(self) -> dict:
        """Exactly the shape sample_submission.json expects."""
        return {
            "category": self.category,
            "status": self.status,
            "review_reason": self.review_reason,
            "has_defect": self.has_defect,
            "defect_fields": self.defect_fields,
        }
