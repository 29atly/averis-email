"""Recognize supported extensions and inspect PDF pages before routing."""
from pathlib import Path

import pymupdf

from .models import FileType, PdfPage, PdfType

# A large scan with only a page number/header should still go through OCR.
SCAN_IMAGE_FRACTION = 0.50
MIN_TEXT_WORDS_ON_IMAGE_PAGE = 20


def recognize_file_type(path: Path) -> FileType:
    return {".pdf": "pdf", ".xlsx": "xlsx", ".txt": "txt"}.get(path.suffix.lower(), "unsupported")


def inspect_pdf(path: Path) -> tuple[PdfType, list[PdfPage]]:
    pages = []
    with pymupdf.open(path) as document:
        if not document.is_pdf:
            raise ValueError("File contents are not a PDF")
        if document.needs_pass:
            raise ValueError("PDF requires a password")
        for number, page in enumerate(document, 1):
            words = [word for word in page.get_text("words") if word[4].strip()]
            images = page.get_image_info()
            area = page.rect.get_area()
            largest = max(((pymupdf.Rect(image["bbox"]) & page.rect).get_area() / area
                           for image in images), default=0) if area > 0 else 0
            if words and not (largest >= SCAN_IMAGE_FRACTION and len(words) < MIN_TEXT_WORDS_ON_IMAGE_PAGE):
                kind = "text"
            elif images or page.get_drawings():
                # Visible content without usable text includes scans and outlined
                # text. Both need OCR; this is a routing heuristic, not provenance.
                kind = "scanned"
            else:
                kind = "blank"
            pages.append(PdfPage(page=number, kind=kind, word_count=len(words),
                                 largest_image_fraction=round(largest, 4)))
    kinds = {page.kind for page in pages} - {"blank"}
    pdf_type = ("mixed" if kinds == {"text", "scanned"} else
                "epdf" if kinds == {"text"} else "scanned" if kinds == {"scanned"} else "empty")
    return pdf_type, pages
