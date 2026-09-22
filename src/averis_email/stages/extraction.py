"""Extract required fields from SI and BL document text."""

import json
import os
import re
import ssl
import certifi
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from dotenv import load_dotenv
from pydantic import BaseModel, Field

from averis_email.schemas import ExtractedDoc, FieldValue, FIELDS


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


# Semantic text fields should be reviewed by the LLM even if
# deterministic extraction already found a value.
SEMANTIC_TEXT_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
    "port_of_loading",
    "port_of_discharge",
}


# Party fields should contain the company / party name rather than
# a full postal address.
PARTY_FIELDS = {
    "shipper",
    "consignee",
    "notify_party",
}


# Build known label list once
LABEL_ENTRIES = []

for _field, _labels in FIELD_LABELS.items():
    for _label in _labels:
        LABEL_ENTRIES.append(
            (_field, _label)
        )


# Longer labels must be checked first.
LABEL_ENTRIES.sort(
    key=lambda item: len(item[1]),
    reverse=True,
)



# Structured NVIDIA result
class LLMField(BaseModel):
    """One field reviewed or extracted by NVIDIA."""

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


class LLMExtraction(BaseModel):
    """Structured NVIDIA result for the seven required fields."""

    shipper: Optional[LLMField] = None
    consignee: Optional[LLMField] = None
    notify_party: Optional[LLMField] = None
    port_of_loading: Optional[LLMField] = None
    port_of_discharge: Optional[LLMField] = None
    container_count: Optional[LLMField] = None
    gross_weight_kg: Optional[LLMField] = None


# ---------------------------------------------------------------------
# NVIDIA provider used only by extraction
# ---------------------------------------------------------------------

class NvidiaExtractionProvider:
    """Small NVIDIA client used only for document extraction."""

    def __init__(
        self,
        api_key: str,
        model: str,
        base_url: str = "https://integrate.api.nvidia.com/v1",
        timeout: int = 120,
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def complete(
        self,
        system: str,
        text: str,
    ) -> str:
        """Send a chat-completion request to NVIDIA."""

        url = f"{self.base_url}/chat/completions"

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": system,
                },
                {
                    "role": "user",
                    "content": text,
                },
            ],
            "temperature": 0,
            "max_tokens": 2048,
            "stream": False,
        }

        request = Request(
            url,
            data=json.dumps(
                payload
            ).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )

        ssl_context = ssl.create_default_context(
            cafile=certifi.where()
        )

        try:
            with urlopen(
                request,
                timeout=self.timeout,
                context=ssl_context,
            ) as response:

                response_text = response.read().decode(
                    "utf-8"
                )

        except HTTPError as exc:

            error_body = exc.read().decode(
                "utf-8",
                errors="replace",
            )

            raise RuntimeError(
                f"NVIDIA HTTP {exc.code}: {error_body}"
            ) from exc

        except URLError as exc:

            raise RuntimeError(
                f"NVIDIA connection failed: {exc.reason}"
            ) from exc

        except TimeoutError as exc:

            raise RuntimeError(
                "NVIDIA request timed out."
            ) from exc

        try:
            response_data = json.loads(
                response_text
            )

        except json.JSONDecodeError as exc:

            raise RuntimeError(
                "NVIDIA returned an invalid API response: "
                f"{response_text}"
            ) from exc

        try:
            message = response_data[
                "choices"
            ][0]["message"]

            result_text = message.get(
                "content",
                "",
            )

        except (
            KeyError,
            IndexError,
            TypeError,
        ) as exc:

            raise RuntimeError(
                "Unexpected NVIDIA response structure: "
                f"{response_data}"
            ) from exc

        if not result_text:
            raise RuntimeError(
                "NVIDIA returned an empty response."
            )

        return result_text.strip()


# ---------------------------------------------------------------------
# Empty field structure
# ---------------------------------------------------------------------

def _empty_fields(
    source_file: str,
) -> dict:
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


# ---------------------------------------------------------------------
# Deterministic extraction helpers
# ---------------------------------------------------------------------

def _annotation_pattern() -> str:
    """Allow optional annotations following a field label."""

    return r"(?:\s*\([^)]*\))*"


def _match_field_label(
    line: str,
):
    """Check whether a line starts with a required field label."""

    annotation = _annotation_pattern()

    for field, label in LABEL_ENTRIES:

        escaped = re.escape(
            label
        )

        # Example:
        # Port of Loading: PORT KLANG
        # Load Port | PORT KLANG
        # Load Port - PORT KLANG
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

        # Example:
        # Port of Loading PORT KLANG
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

        # Example:
        #
        # Port of Loading
        # PORT KLANG
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


def _looks_like_other_label(
    line: str,
) -> bool:
    """Check whether a line appears to start another document field."""

    stripped = line.strip()

    if not stripped:
        return False

    if _match_field_label(
        stripped
    ) is not None:
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


def _is_separator_line(
    line: str,
) -> bool:
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


def _clean_rule_value(
    field: str,
    value: str,
) -> str:
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


def _find_next_value_line(
    lines: list[str],
    start_index: int,
):
    """Find the next usable line after a label-only line."""

    j = start_index

    while j < len(lines):

        candidate = lines[j]

        if _is_separator_line(
            candidate
        ):
            j += 1
            continue

        # Another field has started before a value was found.
        if _looks_like_other_label(
            candidate
        ):
            return None, j

        return candidate.strip(), j

    return None, j


def _is_ambiguous_weight_heading(
    field: str,
    line: str,
    first_value: str,
) -> bool:
    """Avoid treating a table heading as total gross weight."""

    if field != "gross_weight_kg":
        return False

    if first_value:
        return False

    upper = line.upper()

    # Explicit TOTAL labels can be trusted.
    if "TOTAL" in upper:
        return False

    # A generic heading such as GROSS WEIGHT (KG) with no value may only be a table column heading.
    return True


# Deterministic extraction
def _extract_with_rules(
    raw_text: str,
    source_file: str,
) -> dict:
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

        # Keep the first successfully extracted occurrence.
        if extracted[field].value:
            i += 1
            continue

        # Avoid using a table heading as the shipment total weight.
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



# Determine what NVIDIA should inspect
def _find_missing(
    extracted: dict,
) -> list[str]:
    """Return fields that deterministic rules did not extract."""

    missing = []

    for field in FIELDS:

        field_data = extracted.get(
            field
        )

        if (
            field_data is None
            or field_data.value is None
            or not str(
                field_data.value
            ).strip()
        ):
            missing.append(
                field
            )

    return missing


def _fields_for_llm(
    extracted: dict,
) -> list[str]:
    """Return fields NVIDIA should inspect."""

    missing = set(
        _find_missing(
            extracted
        )
    )

    review = []

    for field in FIELDS:

        if (
            field in SEMANTIC_TEXT_FIELDS
            or field in missing
        ):
            review.append(
                field
            )

    return review



# Evidence verification
def _normalize_whitespace(
    text: str,
) -> str:
    """Collapse whitespace for reliable evidence checking."""

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


def _evidence_exists(
    raw_text: str,
    evidence: Optional[str],
) -> bool:
    """Check whether NVIDIA evidence actually exists in the document."""

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


def _evidence_supports_value(
    evidence: Optional[str],
    value: Optional[str],
) -> bool:
    """Check whether evidence contains the extracted value."""

    if (
        not evidence
        or value is None
    ):
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



# JSON response cleaning
def _clean_json_response(
    result_text: str,
) -> str:
    """Remove optional Markdown code fences around NVIDIA JSON."""

    result_text = result_text.strip()

    if result_text.startswith("```"):

        result_text = re.sub(
            r"^```(?:json)?\s*",
            "",
            result_text,
            flags=re.IGNORECASE,
        )

        result_text = re.sub(
            r"\s*```$",
            "",
            result_text,
        )

    return result_text.strip()



# NVIDIA semantic fallback
def _extract_with_nvidia(
    raw_text: str,
    fields_to_review: list[str],
) -> Optional[LLMExtraction]:
    """Use NVIDIA for semantic extraction and placeholder detection."""

    api_key = os.getenv(
        "NVIDIA_EXTRACTION_API_KEY"
    )

    # Prefer an extraction-specific model.
    # Otherwise use the team's NVIDIA model if one is configured.
    model = (
        os.getenv(
            "NVIDIA_EXTRACTION_MODEL"
        )
        or os.getenv(
            "NVIDIA_MODEL"
        )
    )

    base_url = (
        os.getenv(
            "NVIDIA_EXTRACTION_BASE_URL"
        )
        or os.getenv(
            "NVIDIA_BASE_URL"
        )
        or "https://integrate.api.nvidia.com/v1"
    )

    if not api_key:
        raise ValueError(
            "NVIDIA_EXTRACTION_API_KEY is not set."
        )

    if not model:
        raise ValueError(
            "Set NVIDIA_EXTRACTION_MODEL or NVIDIA_MODEL."
        )

    provider = NvidiaExtractionProvider(
        api_key=api_key,
        model=model,
        base_url=base_url,
        timeout=120,
    )

    prompt = f"""
You are extracting information from a Shipping Instruction (SI)
or Bill of Lading (BL).

Only use information explicitly written in the document.

The document may use different wording for the same concept.

Examples:
- "Departure Location" may mean port_of_loading.
- "Arrival Harbor" may mean port_of_discharge.
- "Equipment Count" may mean container_count.
- "Total Cargo Mass" may mean gross_weight_kg.

These examples are only guidance.
Use the meaning of the document text.

Do not guess.
Do not invent information.
Do not infer a value that is not written in the document.
Do not compare this document with another document.
Do not normalize extracted values.

You need to review these fields:

{", ".join(fields_to_review)}

For every reviewed field return:

1. value
   The actual value explicitly written in the document.
   Return null when there is no genuine value.

2. evidence
   The exact text from the document supporting the result.
   Do not rewrite or paraphrase the evidence.
   Return null if there is no relevant text.

3. unresolved
   true when the real value is unavailable or the document only contains
   a placeholder.

Examples of unresolved wording include:
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

This list is not exhaustive.

Important:
- Do not mark a genuine company name unresolved.
- Do not mark a genuine port name unresolved.
- Be conservative.
- Only use unresolved=true when the wording clearly means that the
  real value is missing or not yet known.

For shipper, consignee and notify_party:
- return only the party/company name.
- do not include the postal address.
- preserve the company name as written.

For port_of_loading:
- return the actual departure/loading port or location as written.

For port_of_discharge:
- return the actual arrival/discharge port or location as written.

For container_count:
- preserve the complete expression as written.
- example: "3 x 40FT Containers".

For gross_weight_kg:
- extract the TOTAL shipment gross weight.
- do not use an individual container weight.
- preserve the value and unit as written.

Return ONLY valid JSON.

Use this exact JSON structure:

{{
  "shipper": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "consignee": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "notify_party": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "port_of_loading": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "port_of_discharge": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "container_count": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }},
  "gross_weight_kg": {{
    "value": null,
    "evidence": null,
    "unresolved": false
  }}
}}

For fields that are NOT in the review list, their values may remain null.

DOCUMENT:

{raw_text}
"""

    result_text = provider.complete(
        system=(
            "Extract structured fields from shipping documents. "
            "Return only valid JSON and no additional explanation."
        ),
        text=prompt,
    )

    result_text = _clean_json_response(
        result_text
    )

    try:
        result_json = json.loads(
            result_text
        )

    except json.JSONDecodeError as exc:

        raise RuntimeError(
            "NVIDIA returned invalid JSON: "
            f"{result_text}"
        ) from exc

    try:
        return LLMExtraction.model_validate(
            result_json
        )

    except Exception as exc:

        raise RuntimeError(
            "NVIDIA JSON does not match the expected extraction structure: "
            f"{result_json}"
        ) from exc



# Apply verified NVIDIA results

def _apply_llm_result(
    extracted: dict,
    llm_result: LLMExtraction,
    fields_to_review: list[str],
    raw_text: str,
    source_file: str,
) -> None:
    """Apply NVIDIA results without blindly trusting the model."""

    for field in fields_to_review:

        llm_field = getattr(
            llm_result,
            field,
            None,
        )

        if llm_field is None:
            continue

        current = extracted.get(
            field
        )

        current_value = (
            current.value
            if isinstance(
                current,
                FieldValue,
            )
            else None
        )

        evidence = llm_field.evidence


        # Rules already found a value.
        if (
            current_value is not None
            and str(
                current_value
            ).strip()
        ):

            if (
                field in SEMANTIC_TEXT_FIELDS
                and llm_field.unresolved
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

            # Otherwise keep deterministic result.
            continue


        # Rules did not find a value and NVIDIA says it is unresolved.
        if llm_field.unresolved:

            # Preserve explicit placeholder evidence where available.
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

        # Rules missed the field and NVIDIA returned a real value.

        if (
            llm_field.value is None
            or not str(
                llm_field.value
            ).strip()
        ):
            continue

        # The quoted evidence must really exist in the document.
        if not _evidence_exists(
            raw_text,
            evidence,
        ):
            continue

        # The returned value must also be present inside that evidence.
        if not _evidence_supports_value(
            evidence,
            llm_field.value,
        ):
            continue

        value = _clean_rule_value(
            field,
            str(
                llm_field.value
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


# ---------------------------------------------------------------------
# Public extraction function
# ---------------------------------------------------------------------

def extract_fields(
    doc: ExtractedDoc,
) -> ExtractedDoc:
    """Extract the seven required shipping fields from one document."""

    # If ingestion already marked the document unreadable,
    # extraction should stop here.
    if not doc.readable:
        return doc

    raw_text = doc.fields.get(
        "_raw"
    )

    if (
        not isinstance(
            raw_text,
            str,
        )
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

    # Deterministic extraction using known labels.

    extracted = _extract_with_rules(
        raw_text,
        doc.attachment_path,
    )

    # Determine which fields NVIDIA should inspect.

    fields_to_review = _fields_for_llm(
        extracted
    )

    # NVIDIA semantic fallback.
    if fields_to_review:

        try:

            nvidia_result = _extract_with_nvidia(
                raw_text,
                fields_to_review,
            )

            if nvidia_result is not None:

                # -------------------------------------------------
                # Step 4:
                # Verify NVIDIA output against source evidence.
                # -------------------------------------------------

                _apply_llm_result(
                    extracted=extracted,
                    llm_result=nvidia_result,
                    fields_to_review=fields_to_review,
                    raw_text=raw_text,
                    source_file=doc.attachment_path,
                )

        except Exception as exc:

            # Rules still survive even if NVIDIA fails.
            doc.error = (
                "NVIDIA extraction fallback failed: "
                f"{exc}"
            )

    doc.fields = extracted

    return doc