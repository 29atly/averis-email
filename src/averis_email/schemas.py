"""Shared data contracts for the pipeline.

Every stage module in `averis_email.stages` should accept/return objects
shaped like these. Agree on this file with the whole team before anyone
writes real stage logic -- it's the contract everything else plugs into.
"""
from dataclasses import dataclass, field
from typing import Optional

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


@dataclass
class FieldValue:
    """One extracted field, with evidence so a human reviewer can check it."""
    value: Optional[str]
    source_file: Optional[str] = None
    source_page: Optional[int] = None
    raw_text: Optional[str] = None


@dataclass
class ExtractedDoc:
    """Everything pulled from one SI or BL attachment."""
    attachment_path: str
    doc_type: Optional[str] = None      # "SI" | "BL" | None if undetermined
    fields: dict = field(default_factory=dict)   # field_name -> FieldValue
    readable: bool = True
    error: Optional[str] = None


@dataclass
class PipelineResult:
    email_id: str
    category: str
    status: Optional[str] = None
    review_reason: Optional[str] = None
    has_defect: bool = False
    defect_fields: list = field(default_factory=list)

    si: Optional[ExtractedDoc] = None
    bl: Optional[ExtractedDoc] = None
    diff_detail: dict = field(default_factory=dict)
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
