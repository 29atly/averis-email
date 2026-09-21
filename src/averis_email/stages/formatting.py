"""Stage 5: format the final response for humans.

Owner: Backend/Integration lead.

Contract
--------
to_submission_entry(result: PipelineResult) -> dict
    Thin wrapper around PipelineResult.to_submission_entry() -- kept here
    as its own function so report/UI code can import from `formatting`
    without reaching into schemas directly.

human_readable(result: PipelineResult) -> str
    One-line-per-email summary for the review UI / demo, e.g.
    "email_004: MISMATCH on container_count (SI: 3 / BL: 4)"

Works with comparison.py's per-field diff_detail shape:
    {field_name: {"si_value":.., "bl_value":.., "si_normalized":..,
                  "bl_normalized":.., "match":.., "si_source":{...},
                  "bl_source":{...}}}
plus the orchestrator's "attachment_warnings" and "missing_fields" keys
that can also show up in diff_detail.
"""
from averis_email.schemas import PipelineResult


def to_submission_entry(result: PipelineResult) -> dict:
    return result.to_submission_entry()


def _field_line(field: str, info: dict) -> str:
    si_val = info.get("si_value")
    bl_val = info.get("bl_value")
    return f"{field} (SI: {si_val!r} / BL: {bl_val!r})"


def human_readable(result: PipelineResult) -> str:
    """Build a single readable line describing this email's outcome,
    including any nonblocking attachment warnings if present."""
    warnings = result.diff_detail.get("attachment_warnings") if result.diff_detail else None
    warning_suffix = f"  [warnings: {'; '.join(warnings)}]" if warnings else ""

    if result.category != "BL_COMPARISON":
        return f"{result.email_id}: {result.category}{warning_suffix}"

    if result.status == "NEEDS_REVIEW":
        reason = result.review_reason or "unspecified"
        extra = ""
        missing = result.diff_detail.get("missing_fields") if result.diff_detail else None
        if missing:
            extra = f" (missing: {', '.join(missing)})"
        return f"{result.email_id}: NEEDS_REVIEW ({reason}){extra}{warning_suffix}"

    if result.status == "OK":
        return f"{result.email_id}: OK - No mismatch detected{warning_suffix}"

    # MISMATCH: pull only the fields that actually differ. Support both the
    # richer per-field diff_detail shape from comparison.py (has "match")
    # and a simpler {"si":.., "bl":..} shape, in case that ever changes.
    parts = []
    for field in result.defect_fields:
        info = result.diff_detail.get(field, {})
        if "si_value" in info:
            parts.append(_field_line(field, info))
        elif "si" in info:
            parts.append(f"{field} (SI: {info.get('si')!r} / BL: {info.get('bl')!r})")
        else:
            parts.append(field)
    return f"{result.email_id}: MISMATCH - " + "; ".join(parts) + warning_suffix


def build_report(results: list) -> str:
    """One line per email plus a summary count at the top -- the
    'human-readable report' half of Stage 8 (the other half is
    submission.json). Takes a list of PipelineResult."""
    lines = [human_readable(r) for r in results]

    comparisons = [r for r in results if r.category == "BL_COMPARISON"]
    ok = sum(1 for r in comparisons if r.status == "OK")
    mismatch = sum(1 for r in comparisons if r.status == "MISMATCH")
    review = sum(1 for r in comparisons if r.status == "NEEDS_REVIEW")

    summary = (
        f"Total emails: {len(results)}  |  "
        f"Comparisons: {len(comparisons)} "
        f"(OK: {ok}, MISMATCH: {mismatch}, NEEDS_REVIEW: {review})"
    )
    return summary + "\n" + "-" * len(summary) + "\n" + "\n".join(lines)
