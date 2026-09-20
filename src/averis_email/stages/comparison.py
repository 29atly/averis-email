"""Stage 4: compare normalized SI and BL fields."""

from averis_email.schemas import FIELDS, FieldValue
from averis_email.stages.normalizer import NORMALIZERS


def _get_value(doc, field):
    field_data = doc.fields.get(field)

    if isinstance(field_data, FieldValue):
        return field_data.value

    if isinstance(field_data, dict):
        return field_data.get("value")

    return field_data


def _get_evidence(doc, field):
    field_data = doc.fields.get(field)

    if isinstance(field_data, FieldValue):
        return {
            "source_file": field_data.source_file,
            "source_page": field_data.source_page,
            "raw_text": field_data.raw_text,
        }

    if isinstance(field_data, dict):
        return {
            "source_file": field_data.get("source_file"),
            "source_page": field_data.get("source_page"),
            "raw_text": field_data.get("raw_text"),
        }

    return {
        "source_file": doc.attachment_path,
        "source_page": None,
        "raw_text": None,
    }


def compare_fields(si, bl) -> tuple[list[str], dict]:
    defects = []
    detail = {}

    for field in FIELDS:
        si_value = _get_value(si, field)
        bl_value = _get_value(bl, field)

        normalizer = NORMALIZERS[field]

        si_normalized = normalizer(si_value)
        bl_normalized = normalizer(bl_value)

        is_match = si_normalized == bl_normalized

        if not is_match:
            defects.append(field)

        detail[field] = {
            "si_value": si_value,
            "bl_value": bl_value,
            "si_normalized": si_normalized,
            "bl_normalized": bl_normalized,
            "match": is_match,
            "si_source": _get_evidence(si, field),
            "bl_source": _get_evidence(bl, field),
        }

    return defects, detail