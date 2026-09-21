"""Extract required fields from SI and BL document text."""

import os
import re
from typing import Optional

from dotenv import load_dotenv
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from averis_email.schemas import ExtractedDoc, FieldValue, FIELDS


# Load GEMINI_API_KEY from .env 
load_dotenv()


# Known label variations
FIELD_LABELS = {
    "shipper": [
        "Shipper (Principal or Seller)",
        "Shipper/Exporter",
        "Shipper",
        "Exporter",
        "Seller",
    ],

    "consignee": [
        "Consignee (Non-Negotiable)",
        "To the Order of",
        "Consignee",
    ],

    "notify_party": [
        "Notify Party/Intermediate Consignee",
        "Notify Party",
        "Notify",
    ],

    "port_of_loading": [
        "Port of Loading (POL)",
        "Port of Loading",
        "Load Port",
        "POL",
    ],

    "port_of_discharge": [
        "Port of Discharge (POD)",
        "Port of Discharge",
        "Discharge Port",
        "POD",
    ],

    "container_count": [
        "No. of Containers or Packages",
        "No. of Containers",
        "Total Containers",
        "Container Count",
        "Containers",
    ],

    "gross_weight_kg": [
        "TOTAL Gross Weight■■(KGS)",
        "TOTAL Gross Weight (KGS)",
        "TOTAL Gross Weight (KG)",
        "TOTAL Gross Wt (kgs)",
        "TOTAL GROSS WEIGHT",
        "Gross Weight毛重(KGS)",
        "Gross Weight (KG)",
        "Gross Weight (KGS)",
        "Gross Wt (kgs)",
        "Gross Weight",
        "GROSS WEIGHT",
    ],
}


# These fields contain semantic text.
# Even when rules find a non-empty value, Gemini reviews these fields
SEMANTIC_TEXT_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
}


# Party fields should contain the party/company name only rather than the full address.
PARTY_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
}


# Build the label list once.
LABEL_ENTRIES = []

for _field, _labels in FIELD_LABELS.items():
    for _label in _labels:
        LABEL_ENTRIES.append(
            (_field, _label)
        )

# Longer labels should be checked first.
LABEL_ENTRIES.sort(
    key=lambda item: len(item[1]),
    reverse=True,
)


# Gemini structured output
class GeminiField(BaseModel):
    """One field reviewed or extracted by Gemini."""

    value: Optional[str] = Field(
        default=None,
        description=(
            "Actual value explicitly written in the document. "
            "Null when the real value is missing or unresolved."
        ),
    )

    evidence: Optional[str] = Field(
        default=None,
        description=(
            "Exact text from the document supporting the decision."
        ),
    )

    unresolved: bool = Field(
        default=False,
        description=(
            "True when the document does not provide the real value "
            "and instead contains a placeholder or unresolved wording."
        ),
    )


class GeminiExtraction(BaseModel):
    """Structured Gemini result for the seven required fields."""

    shipper: Optional[GeminiField] = None
    consignee: Optional[GeminiField] = None
    notify_party: Optional[GeminiField] = None
    port_of_loading: Optional[GeminiField] = None
    port_of_discharge: Optional[GeminiField] = None
    container_count: Optional[GeminiField] = None
    gross_weight_kg: Optional[GeminiField] = None


def _empty_fields(source_file: str) -> dict:
    """Create empty FieldValue objects for all required fields."""

    return {
        field: FieldValue(
            value=None,
            source_file=source_file,
            source_page=None,
            raw_text=None,
        )
        for field in FIELDS
    }


def _annotation_pattern() -> str:
    """Allow optional annotations following a field label.

    Examples:

    Shipper/Exporter (发货人)
    Gross Wt (kgs) (毛重 KGS)
    """

    return r"(?:\s*\([^)]*\))*"


def _match_field_label(line: str):
    """Check whether a line starts with a required field label.

    Supported forms include:

    Shipper: ABC TRADING
    Shipper - ABC TRADING
    Shipper | ABC TRADING
    Shipper<TAB>ABC TRADING
    Shipper ABC TRADING

    It also supports:

    Shipper
    ABC TRADING
    """

    annotation = _annotation_pattern()

    for field, label in LABEL_ENTRIES:
        escaped = re.escape(label)

        # ---------------------------------------------------------
        # Case 1:
        #
        # Label: Value
        # Label - Value
        # Label | Value
        # Label<TAB>Value
        # ---------------------------------------------------------

        pattern = (
            rf"^\s*{escaped}"
            rf"{annotation}"
            rf"\s*(?::|\||\t|-)\s*(.*?)\s*$"
        )

        match = re.match(
            pattern,
            line,
            re.IGNORECASE,
        )

        if match:
            return (
                field,
                match.group(1).strip(),
            )

        # ---------------------------------------------------------
        # Case 2:
        #
        # Label Value
        #
        # Example:
        # Load Port PORT KLANG
        # ---------------------------------------------------------

        pattern = (
            rf"^\s*{escaped}"
            rf"{annotation}"
            rf"\s+(.+?)\s*$"
        )

        match = re.match(
            pattern,
            line,
            re.IGNORECASE,
        )

        if match:
            return (
                field,
                match.group(1).strip(),
            )

        # ---------------------------------------------------------
        # Case 3:
        #
        # Label
        # Value appears on following line.
        # ---------------------------------------------------------

        pattern = (
            rf"^\s*{escaped}"
            rf"{annotation}"
            rf"\s*$"
        )

        if re.match(
            pattern,
            line,
            re.IGNORECASE,
        ):
            return field, ""

    return None


def _looks_like_other_label(line: str) -> bool:
    """Check whether a line appears to start another document field."""

    stripped = line.strip()

    if not stripped:
        return False

    if _match_field_label(stripped) is not None:
        return True

    return bool(
        re.match(
            r"^\s*"
            r"[A-Za-z][A-Za-z0-9 /().,&_\-]{1,60}"
            r"\s*(?::|\||\t|\s-\s)"
            r"\s*",
            stripped,
        )
    )


def _is_separator_line(line: str) -> bool:
    """Return True for empty or separator lines."""

    stripped = line.strip()

    if not stripped:
        return True

    return bool(
        re.fullmatch(
            r"[-=_|]+",
            stripped,
        )
    )


def _clean_rule_value(field: str, value: str,) -> str:
    """Clean structural formatting without normalizing field meaning."""

    value = value.strip()

    if not value:
        return ""

    if field in PARTY_FIELDS:

        if "|" in value:
            value = value.split(
                "|",
                1,
            )[0].strip()

        if "\t" in value:
            value = value.split(
                "\t",
                1,
            )[0].strip()

    return value


def _find_next_value_line(lines: list[str], start_index: int,):
    """Find the next usable line after a label-only line."""

    j = start_index

    while j < len(lines):
        candidate = lines[j]

        # Skip blank/separator lines.
        if _is_separator_line(candidate):
            j += 1
            continue

        # Another field started before a value was found.
        if _looks_like_other_label(candidate):
            return None, j

        return candidate.strip(), j

    return None, j


def _is_ambiguous_weight_heading(field: str, line: str, first_value: str,) -> bool:
    """Avoid treating a table heading as total gross weight.

    Example:

        CONTAINER NO.   DESCRIPTION   GROSS WEIGHT (KG)

    followed by individual container weights.

    A generic Gross Weight heading with no value should therefore
    be left unresolved. Gemini can later locate the shipment total.

    Explicit TOTAL Gross Weight labels are allowed.
    """

    if field != "gross_weight_kg":
        return False

    if first_value:
        return False

    upper = line.upper()

    if "TOTAL" in upper:
        return False

    return True


def _extract_with_rules(raw_text: str, source_file: str,) -> dict:
    """Extract fields using deterministic field-label rules."""

    extracted = _empty_fields(
        source_file
    )

    lines = raw_text.splitlines()

    i = 0

    while i < len(lines):

        line = lines[i]

        matched = _match_field_label(
            line
        )

        if matched is None:
            i += 1
            continue

        field, first_value = matched

        # Keep first successfully extracted occurrence.
        if extracted[field].value:
            i += 1
            continue

        # Avoid using a PDF table heading as total weight.
        if _is_ambiguous_weight_heading(
            field,
            line,
            first_value,
        ):
            i += 1
            continue

        evidence_lines = [
            line.strip()
        ]

        value = _clean_rule_value(
            field,
            first_value,
        )

        # Label and value may be on separate lines.
        if not value:

            next_value, next_index = _find_next_value_line(
                lines,
                i + 1,
            )

            if next_value is not None:

                value = _clean_rule_value(
                    field,
                    next_value,
                )

                evidence_lines.append(
                    lines[next_index].strip()
                )

                i = next_index

        if value:

            extracted[field] = FieldValue(
                value=value,
                source_file=source_file,
                source_page=None,
                raw_text="\n".join(
                    evidence_lines
                ),
            )

        i += 1

    return extracted


# Determine what Gemini needs to inspect
def _find_missing(
    extracted: dict,
) -> list[str]:
    """Return fields that rules did not extract."""

    missing = []

    for field in FIELDS:

        field_data = extracted.get(
            field
        )

        if (
            field_data is None
            or field_data.value is None
            or str(
                field_data.value
            ).strip() == ""
        ):
            missing.append(field)

    return missing


def _fields_for_gemini(extracted: dict,) -> list[str]:
    """Return fields Gemini should inspect."""

    missing = set(
        _find_missing(extracted)
    )

    review = []

    for field in FIELDS:

        if (
            field in SEMANTIC_TEXT_FIELDS
            or field in missing
        ):
            review.append(field)

    return review


# Evidence verification
def _normalize_whitespace(text: str,) -> str:
    """Collapse whitespace for reliable evidence checking."""

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _evidence_exists(raw_text: str, evidence: Optional[str],) -> bool:
    """Check whether Gemini evidence exists in the document."""

    if not evidence:
        return False

    document_text = _normalize_whitespace(
        raw_text
    ).casefold()

    evidence_text = _normalize_whitespace(
        evidence
    ).casefold()

    return (
        evidence_text
        in document_text
    )


def _evidence_supports_value(evidence: Optional[str], value: Optional[str],) -> bool:
    """Check whether evidence contains the value being reviewed."""

    if not evidence or value is None:
        return False

    evidence_text = _normalize_whitespace(
        evidence
    ).casefold()

    value_text = _normalize_whitespace(
        str(value)
    ).casefold()

    return (
        value_text
        in evidence_text
    )


# Gemini extraction / semantic review
def _extract_with_gemini(
    raw_text: str,
    fields_to_review: list[str],
) -> Optional[GeminiExtraction]:
    """Use Gemini for missing fields and semantic placeholder checking."""

    api_key = os.getenv(
        "GEMINI_API_KEY"
    )

    if not api_key:
        return None

    client = genai.Client(
        api_key=api_key
    )

    prompt = f"""
You are reviewing fields from a Shipping Instruction (SI)
or Bill of Lading (BL).

Only use information explicitly present in the document.

Do not guess.
Do not invent information.
Do not infer a missing value from unrelated information.
Do not compare this document with another document.
Do not normalize ports, weights, or container values.

You have two jobs:

1. Extract a field if its real value is present.
2. Detect when text is only a placeholder or means that the real value
   is not yet known.

A field is unresolved when the document contains wording that means
the real value has not been provided yet.

Examples include, but are NOT limited to:

- N/A
- TBD
- TBA
- unknown
- pending
- pending confirmation
- to be advised
- to be confirmed
- awaiting confirmation
- awaiting nomination
- will advise
- to follow
- not available
- blank placeholders
- underscores
- question marks

These examples are not an exhaustive list.

Use the meaning of the wording to decide whether the field contains
a genuine value or merely indicates that the value is unavailable.

Important:
- Do NOT mark a genuine company name or genuine port name unresolved.
- Do NOT mark normal shipping terminology unresolved merely because
  it sounds unusual.
- Be conservative. Only mark unresolved=True when the wording clearly
  indicates that the real value is missing or not yet known.

For shipper, consignee, and notify_party:
- return only the party/company name.
- do not include the postal address.
- preserve the company name as written.

For port_of_loading and port_of_discharge:
- return the actual port/location as written.
- if the document only says something like "TO BE ADVISED",
  return value=null and unresolved=true.

For container_count:
- preserve the complete expression as written.
- example: "15 x 20'GP".

For gross_weight_kg:
- extract the TOTAL gross weight for the shipment.
- do not use an individual container weight.
- preserve the value and unit as written.

For every field:
- evidence must be an exact quote from the document.
- if a genuine value is present:
    unresolved=false
    value=<actual value>
- if the field is clearly a placeholder or unresolved:
    unresolved=true
    value=null
- if the field does not appear at all:
    unresolved=true
    value=null
    evidence=null

Only review these fields:

{", ".join(fields_to_review)}

DOCUMENT:

{raw_text}
"""

    response = client.models.generate_content(
        model="gemini-3.5-flash-lite",
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0,
            response_mime_type="application/json",
            response_schema=GeminiExtraction,
        ),
    )

    return response.parsed


# ---------------------------------------------------------------------
# Apply verified Gemini results
# ---------------------------------------------------------------------

def _apply_gemini_result(
    extracted: dict,
    gemini_result: GeminiExtraction,
    fields_to_review: list[str],
    raw_text: str,
    source_file: str,
) -> None:
    """Apply Gemini results without blindly trusting the model."""

    for field in fields_to_review:

        gemini_field = getattr(
            gemini_result,
            field,
            None,
        )

        if gemini_field is None:
            continue

        current = extracted.get(
            field
        )

        current_value = (
            current.value
            if isinstance(current, FieldValue)
            else None
        )

        evidence = (
            gemini_field.evidence
        )


        # CASE 1: Rules already found a value.
        if (
            current_value is not None
            and str(current_value).strip()
        ):

            if (
                field in SEMANTIC_TEXT_FIELDS
                and gemini_field.unresolved
                and _evidence_exists(
                    raw_text,
                    evidence,
                )
                and _evidence_supports_value(
                    evidence,
                    current_value,
                )
            ):

                extracted[field] = FieldValue(
                    value=None,
                    source_file=source_file,
                    source_page=None,
                    raw_text=evidence,
                )

            # Keep the value found by the rules.
            continue

        # CASE 2: Rule extraction could not find a value.
        if gemini_field.unresolved:

            # Preserve evidence if Gemini found an explicit placeholder.
            if (
                evidence
                and _evidence_exists(
                    raw_text,
                    evidence,
                )
            ):

                extracted[field] = FieldValue(
                    value=None,
                    source_file=source_file,
                    source_page=None,
                    raw_text=evidence,
                )

            continue

        if (
            gemini_field.value is None
            or not str(
                gemini_field.value
            ).strip()
        ):
            continue

        if not _evidence_exists(
            raw_text,
            evidence,
        ):
            continue

        value = _clean_rule_value(
            field,
            str(
                gemini_field.value
            ),
        )

        if not value:
            continue

        extracted[field] = FieldValue(
            value=value,
            source_file=source_file,
            source_page=None,
            raw_text=evidence,
        )


# Public extraction function
def extract_fields(doc: ExtractedDoc,) -> ExtractedDoc:
    """Extract the seven required shipping fields from one document."""

    # If ingestion already marked the document unreadable, extraction should not continue.
    if not doc.readable:
        return doc

    raw_text = doc.fields.get(
        "_raw"
    )

    if (
        not isinstance(raw_text, str)
        or not raw_text.strip()
    ):

        doc.readable = False

        doc.error = (
            doc.error
            or (
                "No readable document text "
                "was provided by ingestion."
            )
        )

        doc.fields = _empty_fields(
            doc.attachment_path
        )

        return doc

    extracted = _extract_with_rules(
        raw_text,
        doc.attachment_path,
    )



    fields_to_review = _fields_for_gemini(
        extracted
    )



    if fields_to_review:

        try:

            gemini_result = _extract_with_gemini(
                raw_text,
                fields_to_review,
            )

            if gemini_result is not None:

                _apply_gemini_result(
                    extracted=extracted,
                    gemini_result=gemini_result,
                    fields_to_review=fields_to_review,
                    raw_text=raw_text,
                    source_file=doc.attachment_path,
                )

        except Exception as exc:


            doc.error = (
                "Gemini extraction fallback failed: "
                f"{exc}"
            )

    doc.fields = extracted

    return doc