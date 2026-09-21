"""normalize extracted shipping document fields."""

import re
from typing import Optional


def norm_name(value) -> Optional[str]:
    if value is None:
        return None

    text = str(value)
    text = re.sub(r"\s+", " ", text)
    text = text.strip(" .,;:")

    return text.upper() or None


def norm_port(value) -> Optional[str]:
    if value is None:
        return None

    text = str(value)
    text = re.sub(r"\s+", " ", text).strip()
    text = text.upper()

    text = re.sub(r"\s*\([A-Z]{2}[A-Z0-9]{3}\)\s*$", "", text)

    return text.strip(" .,;:") or None


def norm_container(value) -> Optional[int]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return int(value)

    match = re.search(r"\d+", str(value))

    if not match:
        return None

    return int(match.group())


def norm_weight(value) -> Optional[float]:
    if value is None:
        return None

    if isinstance(value, (int, float)):
        return float(value)

    text = str(value).upper().replace(",", "")

    match = re.search(r"\d+(?:\.\d+)?", text)

    if not match:
        return None

    number = float(match.group())

    if (
        "TONNE" in text
        or "TONNES" in text
        or re.search(r"\bMT\b", text)
    ):
        number *= 1000

    return number


NORMALIZERS = {
    "shipper": norm_name,
    "consignee": norm_name,
    "notify_party": norm_name,
    "port_of_loading": norm_port,
    "port_of_discharge": norm_port,
    "container_count": norm_container,
    "gross_weight_kg": norm_weight,
}