"""validate required extracted shipping fields."""

from averis_email.schemas import FIELDS, FieldValue
from averis_email.stages.normalizer import NORMALIZERS


# Small list for obvious missing values.
# Gemini handles unusual semantic placeholders earlier in extraction.py.
MISSING_TEXT_MARKERS = {
    "N/A",
    "NA",
    "N.A.",
    "NONE",
    "NULL",
    "UNKNOWN",
    "TBD",
    "TBC",
    "TBA",
    "NOT AVAILABLE",
}


def _get_value(doc, field):
    """Return the actual stored value for a field."""

    field_data = doc.fields.get(field)

    if isinstance(field_data, FieldValue):
        return field_data.value

    if isinstance(field_data, dict):
        return field_data.get("value")

    return field_data


def _is_missing_value(field, value) -> bool:
    """Return True when a required field has no usable value."""

    if value is None:
        return True

    text = str(value).strip()

    # Empty string.
    if not text:
        return True

    upper = text.upper()

    if upper in MISSING_TEXT_MARKERS:
        return True

    if field in {
        "container_count",
        "gross_weight_kg",
    }:
        normalizer = NORMALIZERS[field]

        if normalizer(value) is None:
            return True

    return False


def missing_fields(si, bl) -> list[str]:
    """Return required fields missing from either the SI or BL."""

    missing = []

    for field in FIELDS:
        si_value = _get_value(
            si,
            field,
        )

        bl_value = _get_value(
            bl,
            field,
        )

        if (
            _is_missing_value(field, si_value)
            or _is_missing_value(field, bl_value)
        ):
            missing.append(field)

    return missing