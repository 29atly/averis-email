"""Stage 1: classify incoming inbox records.

Owner: Email Intelligence teammate.

Contract
--------
classify_email(email: dict) -> str
    `email` is one inbox record (email_id/from/subject/body/attachments).
    Must return one of averis_email.schemas.CATEGORIES.

find_si_bl(email: dict) -> AttachmentResolutionResult
    Only called for emails already classified as BL_COMPARISON. Must
    explain what it found, not just hand back two paths:
      - si_path / bl_path: the resolved paths, or None if not found
      - review_required + review_reason: set True with a reason
        ("missing_attachment", "ambiguous_attachments", "wrong_doc_type")
        whenever the attachments can't be resolved safely
      - warnings: human-readable notes for the report/review UI, e.g.
        "2 BL candidates found: draft_bl_v1.pdf, draft_bl_v2.pdf"

The two functions below are placeholders (dumb heuristics) so the pipeline
runs end-to-end today. Replace the bodies with real logic -- keep the
signatures identical so nothing else in the codebase needs to change.
"""
from averis_email.schemas import AttachmentResolutionResult


def classify_email(email: dict) -> str:
    subject = (email.get("subject") or "").lower()
    if not email.get("attachments"):
        if "invoice" in subject:
            return "INVOICE_QUERY"
        if any(w in subject for w in ("viagra", "win a", "prize", "lottery")):
            return "SPAM"
        return "GENERAL"
    return "BL_COMPARISON"


def find_si_bl(email: dict) -> AttachmentResolutionResult:
    si_candidates, bl_candidates = [], []
    for path in email.get("attachments", []):
        low = path.lower()
        if "_si." in low:
            si_candidates.append(path)
        elif "_bl." in low:
            bl_candidates.append(path)

    if len(si_candidates) > 1 or len(bl_candidates) > 1:
        # More than one candidate = can't safely pick one, functionally the
        # same problem as not having one at all -- mapped to
        # "missing_attachment" since that's one of the 4 reasons the
        # evaluation format actually accepts.
        return AttachmentResolutionResult(
            review_required=True, review_reason="missing_attachment",
            warnings=[f"SI candidates: {si_candidates}", f"BL candidates: {bl_candidates}"],
        )

    si = si_candidates[0] if si_candidates else None
    bl = bl_candidates[0] if bl_candidates else None
    if not si or not bl:
        return AttachmentResolutionResult(
            si_path=si, bl_path=bl,
            review_required=True, review_reason="missing_attachment",
        )

    return AttachmentResolutionResult(si_path=si, bl_path=bl)
