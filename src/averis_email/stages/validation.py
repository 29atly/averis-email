"""Stage 4: validate extraction confidence and required fields."""

from averis_email.schemas import FIELDS, FieldValue


def _get_value(doc, field):
    field_data = doc.fields.get(field)

    if isinstance(field_data, FieldValue):
        return field_data.value

    if isinstance(field_data, dict):
        return field_data.get("value")

    return field_data


def missing_fields(si, bl) -> list[str]:
    missing = []

    for field in FIELDS:
        si_value = _get_value(si, field)
        bl_value = _get_value(bl, field)

        if (
            si_value is None
            or str(si_value).strip() == ""
            or bl_value is None
            or str(bl_value).strip() == ""
        ):
            missing.append(field)

    return missing