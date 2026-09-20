"""Handler boundaries for adding OCR, spreadsheet and text extraction later."""
from pathlib import Path

from averis_email.stages.extraction import extract_pdf


def extract_epdf(path: Path) -> dict:
    return extract_pdf(path)


def extract_with_ocr(path: Path) -> dict:
    raise NotImplementedError("OCR extraction is not implemented; scanned or mixed PDFs require OCR.")


def extract_xlsx(path: Path) -> dict:
    raise NotImplementedError("XLSX extraction is not implemented.")


def extract_txt(path: Path) -> dict:
    raise NotImplementedError("TXT extraction is not implemented.")
