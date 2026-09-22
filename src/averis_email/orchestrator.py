"""Orchestration only -- calls every stage in order and guarantees a valid
result for every email, even when a stage throws or a document can't be
read. This is the piece that makes five people's separate files into one
working pipeline; it should stay boring and defensive on purpose.
"""
from averis_email.review import review_context
from averis_email.schemas import CATEGORIES, PipelineResult
from averis_email.classifier import ClassificationDecision, classify_email
from averis_email.stages import classification, ingestion, extraction, validation, comparison


def _with_warnings(detail: dict, warnings: list) -> dict:
    """Fold attachment-resolution warnings into a result's diff_detail
    without clobbering whatever else is already in there. A nonblocking
    warning should always survive into the final result, whether or not
    review ends up being required."""
    if not warnings:
        return detail
    return {**detail, "attachment_warnings": warnings}


def run_pipeline(loader, email: dict, *, category_override: str | None = None,
                  attachment_override: tuple[str, str] | None = None) -> PipelineResult:
    eid = email["email_id"]
    stage = 'classification'

    def result(**kwargs):
        if kwargs.get('status') == 'NEEDS_REVIEW':
            kwargs['review_context'] = review_context(email, stage)
        return PipelineResult(**kwargs)

    try:
        if category_override is not None and category_override not in CATEGORIES:
            raise ValueError('Unsupported category override')
        # A reviewer assigning SI/BL roles has already confirmed this is a
        # comparison request -- don't re-run classification (which can hit
        # a non-deterministic LLM/Laya backend) just to re-derive that.
        if attachment_override and category_override is None:
            category_override = 'BL_COMPARISON'
        decision = ClassificationDecision(category_override) if category_override else classify_email(email)
    except Exception as e:
        return result(email_id=eid, category="REVIEW", status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"classify failed: {e}")

    if decision.review_required:
        # Keep classification failures distinct from accepted GENERAL emails.
        # Raw backend diagnostics remain available in diff_detail.
        return result(email_id=eid, category="REVIEW", status="NEEDS_REVIEW",
                              review_reason="unreadable",
                              diff_detail={"classification": decision.details})

    category = decision.category

    if category != "BL_COMPARISON":
        return result(email_id=eid, category=category, status=None)

    stage = 'attachment_resolution'
    resolution = None
    if attachment_override:
        # A human reviewer has already told us which attachment is which --
        # trust that identification instead of re-running the filename
        # heuristics that failed to resolve it automatically.
        si_path, bl_path = attachment_override
        attachment_warnings = []
    else:
        try:
            resolution = classification.find_si_bl(email)
        except Exception as e:
            return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                                   review_reason="unreadable", error=f"find_si_bl failed: {e}")

        # Captured once, carried through every return below -- this is the fix:
        # previously these warnings only survived on the review_required path.
        attachment_warnings = resolution.warnings

        if resolution.review_required:
            return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                                   review_reason=resolution.review_reason,
                                   diff_detail=_with_warnings({}, attachment_warnings))

        si_path, bl_path = resolution.si_path, resolution.bl_path
        if not si_path or not bl_path:
            return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                                   review_reason="missing_attachment",
                                   diff_detail=_with_warnings({}, attachment_warnings))

    stage = 'extraction'
    si_doc = bl_doc = None
    try:
        si_doc = extraction.extract_fields((resolution.si_doc if resolution else None) or ingestion.read_document(loader, si_path))
        bl_doc = extraction.extract_fields((resolution.bl_doc if resolution else None) or ingestion.read_document(loader, bl_path))
    except Exception as e:
        return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", error=f"read/extract failed: {e}", si=si_doc, bl=bl_doc,
                               diff_detail=_with_warnings({}, attachment_warnings))

    if not si_doc.readable or not bl_doc.readable:
        return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="unreadable", si=si_doc, bl=bl_doc,
                               error=si_doc.error or bl_doc.error,
                               diff_detail=_with_warnings({}, attachment_warnings))

    stage = 'validation'
    try:
        missing = validation.missing_fields(si_doc, bl_doc)
    except Exception as exc:
        return result(email_id=eid, category=category, status='NEEDS_REVIEW',
                      review_reason='unreadable', si=si_doc, bl=bl_doc,
                      error=f'validation failed: {exc}', diff_detail=_with_warnings({}, attachment_warnings))
    if missing:
        return result(email_id=eid, category=category, status="NEEDS_REVIEW",
                               review_reason="missing_value", si=si_doc, bl=bl_doc,
                               diff_detail=_with_warnings({"missing_fields": missing}, attachment_warnings))

    stage = 'comparison'
    try:
        defects, detail = comparison.compare_fields(si_doc, bl_doc)
    except Exception as exc:
        return result(email_id=eid, category=category, status='NEEDS_REVIEW',
                      review_reason='unreadable', si=si_doc, bl=bl_doc,
                      error=f'comparison failed: {exc}', diff_detail=_with_warnings({}, attachment_warnings))
    status = "MISMATCH" if defects else "OK"
    return result(email_id=eid, category=category, status=status,
                           has_defect=bool(defects), defect_fields=defects,
                           si=si_doc, bl=bl_doc,
                           diff_detail=_with_warnings(detail, attachment_warnings))
