"""Shared data contracts for the pipeline -- Pydantic models.

Every stage module in `averis_email.stages` should accept/return objects
shaped like these. Agree on this file with the whole team before anyone
writes real stage logic -- it's the contract everything else plugs into.
"""
from typing import Any, Optional

from pydantic import BaseModel, Field

CATEGORIES = ["BL_COMPARISON", "SI_REQUEST", "INVOICE_QUERY", "GENERAL", "SPAM"]
STATUSES = ["OK", "MISMATCH", "NEEDS_REVIEW"]

# The 4 review reasons the evaluation format actually accepts (per your
# bundle's README.md) -- do not add to this list without confirming the
# scorer supports it. Anything more specific gets mapped down to one of
# these before it reaches submission.json.
REVIEW_REASONS = [
    "wrong_doc_type",
    "missing_attachment",
    "unreadable",
    "missing_value",
]

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
    source_file: Optional[str] = None
    source_page: Optional[int] = None
    raw_text: Optional[str] = None


class ExtractedDoc(BaseModel):
    """Everything pulled from one SI or BL attachment.

    `fields` is typed loosely (dict[str, Any]) because stage 2 (ingestion)
    temporarily stores raw text under "_raw" before stage 3 (extraction)
    replaces it with real FieldValue entries keyed by the names in FIELDS.
    """
    attachment_path: str
    doc_type: Optional[str] = None
    fields: dict[str, Any] = Field(default_factory=dict)
    readable: bool = True
    error: Optional[str] = None


class AttachmentResolutionResult(BaseModel):
    """What stage 2's find_si_bl() returns -- richer than a bare
    (si_path, bl_path) tuple so it can explain WHY an attachment couldn't
    be resolved cleanly, not just that it couldn't.

    Only relevant for emails already classified as BL_COMPARISON --
    classification (deciding the category itself) stays classify_email()'s
    job, not this one's.
    """
    si_doc: Optional[ExtractedDoc] = None
    bl_doc: Optional[ExtractedDoc] = None
    si_path: Optional[str] = None
    bl_path: Optional[str] = None
    review_required: bool = False
    review_reason: Optional[str] = None  # one of REVIEW_REASONS, or None
    warnings: list[str] = Field(default_factory=list)  # human-readable notes


class ReviewAttachment(BaseModel):
    path: str
    download_url: str


class ReviewContext(BaseModel):
    stage: str
    original_email: dict[str, Any]
    attachments: list[ReviewAttachment] = Field(default_factory=list)


class PipelineResult(BaseModel):
    review_context: Optional[ReviewContext] = None
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
