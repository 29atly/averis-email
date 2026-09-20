"""Orchestration only -- calls every stage in order and guarantees a valid
result for every email, even when a stage throws or a document can't be
read. This is the piece that makes five people's separate files into one
working pipeline; it should stay boring and defensive on purpose.
"""
from averis_email.schemas import PipelineResult
from averis_email.stages import classification, ingestion, extraction, validation, comparison


def run_pipeline(loader, email: dict) -> PipelineResult:
    eid = email["email_id"]

    try:
        category = classification.classify_email(email)
    except Exception as e:
        return PipelineResult(email_id=eid, category="GENERAL", status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"classify failed: {e}")

    if category != "BL_COMPARISON":
        return PipelineResult(email_id=eid, category=category, status=None)

    si_path, bl_path = classification.find_si_bl(email)
    if not si_path or not bl_path:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="missing_attachment")

    try:
        si_doc = extraction.extract_fields(ingestion.read_document(loader, si_path))
        bl_doc = extraction.extract_fields(ingestion.read_document(loader, bl_path))
    except Exception as e:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"read/extract failed: {e}")

    if not si_doc.readable or not bl_doc.readable:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", si=si_doc, bl=bl_doc,
                               error=si_doc.error or bl_doc.error)

    missing = validation.missing_fields(si_doc, bl_doc)
    if missing:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="missing_value", si=si_doc, bl=bl_doc,
                               diff_detail={"missing_fields": missing})

    defects, detail = comparison.compare_fields(si_doc, bl_doc)
    status = "MISMATCH" if defects else "OK"
    return PipelineResult(email_id=eid, category=category, status=status,
                           has_defect=bool(defects), defect_fields=defects,
                           si=si_doc, bl=bl_doc, diff_detail=detail)
