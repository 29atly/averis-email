"""Orchestration only -- calls every stage in order and guarantees a valid
result for every email, even when a stage throws or a document can't be
read. This is the piece that makes five people's separate files into one
working pipeline; it should stay boring and defensive on purpose.
"""
from averis_email.schemas import PipelineResult
from averis_email.stages import classification, ingestion, extraction, validation, comparison


def _with_warnings(detail: dict, warnings: list) -> dict:
    """Fold attachment-resolution warnings into a result's diff_detail
    without clobbering whatever else is already in there. A nonblocking
    warning should always survive into the final result, whether or not
    review ends up being required."""
    if not warnings:
        return detail
    return {**detail, "attachment_warnings": warnings}


def run_pipeline(loader, email: dict) -> PipelineResult:
    eid = email["email_id"]

    try:
        category = classification.classify_email(email)
    except Exception as e:
        return PipelineResult(email_id=eid, category="GENERAL", status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"classify failed: {e}")

    if category != "BL_COMPARISON":
        return PipelineResult(email_id=eid, category=category, status=None)

    try:
        resolution = classification.find_si_bl(email)
    except Exception as e:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"find_si_bl failed: {e}")

    # Captured once, carried through every return below -- this is the fix:
    # previously these warnings only survived on the review_required path.
    attachment_warnings = resolution.warnings

    if resolution.review_required:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason=resolution.review_reason,
                               diff_detail=_with_warnings({}, attachment_warnings))

    si_path, bl_path = resolution.si_path, resolution.bl_path
    if not si_path or not bl_path:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="missing_attachment",
                               diff_detail=_with_warnings({}, attachment_warnings))

    try:
        si_doc = extraction.extract_fields(ingestion.read_document(loader, si_path))
        bl_doc = extraction.extract_fields(ingestion.read_document(loader, bl_path))
    except Exception as e:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"read/extract failed: {e}",
                               diff_detail=_with_warnings({}, attachment_warnings))

    if not si_doc.readable or not bl_doc.readable:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", si=si_doc, bl=bl_doc,
                               error=si_doc.error or bl_doc.error,
                               diff_detail=_with_warnings({}, attachment_warnings))

    missing = validation.missing_fields(si_doc, bl_doc)
    if missing:
        return PipelineResult(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="missing_value", si=si_doc, bl=bl_doc,
                               diff_detail=_with_warnings({"missing_fields": missing}, attachment_warnings))

    defects, detail = comparison.compare_fields(si_doc, bl_doc)
    status = "MISMATCH" if defects else "OK"
    return PipelineResult(email_id=eid, category=category, status=status,
                           has_defect=bool(defects), defect_fields=defects,
                           si=si_doc, bl=bl_doc,
                           diff_detail=_with_warnings(detail, attachment_warnings))
