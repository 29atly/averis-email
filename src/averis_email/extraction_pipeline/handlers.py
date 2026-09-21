"""Adapters sharing the (path, plan) contract for registry dispatch."""
from pathlib import Path

from .models import RoutingPlan
from . import structured
from .ocr import extract_ocr_pdf


def extract_epdf(path: Path, plan: RoutingPlan) -> dict:
    """Extract text from digital PDF."""
    return extract_ocr_pdf(path, page_details=plan.pages)


def extract_with_ocr(path: Path, plan: RoutingPlan) -> dict:
    """Extract text from scanned or mixed PDF using OCR."""
    return extract_ocr_pdf(path, page_details=plan.pages)


def extract_xlsx(path: Path, plan: RoutingPlan) -> dict:
    """Extract raw text from XLSX."""
    return structured.extract_xlsx(path)


def extract_docx(path: Path, plan: RoutingPlan) -> dict:
    """Extract raw text from DOCX."""
    return structured.extract_docx(path)


def extract_txt(path: Path, plan: RoutingPlan) -> dict:
    """Extract raw text from TXT."""
    return structured.extract_txt(path)


def default_registry():
    return {"pdf_extractor": extract_epdf, "ocr": extract_with_ocr,
            "xlsx": extract_xlsx, "docx": extract_docx, "txt": extract_txt}
