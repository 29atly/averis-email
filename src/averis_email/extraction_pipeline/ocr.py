"""Extract raw text from PDF pages using native text or OCR."""
from pathlib import Path

import pymupdf

from .detection import inspect_pdf, text_quality
from .models import PdfPage


def create_ocr_engine():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("Install OCR dependencies with pip install -e '.[ocr]'") from exc
    return PaddleOCR(lang="en", use_doc_orientation_classify=False,
                     use_doc_unwarping=False, use_textline_orientation=False)


def extract_ocr_pdf(path: str | Path, *, engine=None,
                    dpi: int = 200, min_confidence: float = 0.5,
                    page_details: list[PdfPage] | None = None) -> dict:
    """Extract raw text from PDF using native text or OCR per page."""
    if dpi <= 0:
        raise ValueError("OCR DPI must be positive")
    if not 0 <= min_confidence <= 1:
        raise ValueError("OCR confidence must be between zero and one")

    path = Path(path)
    if page_details is None:
        _, page_details = inspect_pdf(path)
    details = {detail.page: detail for detail in page_details}
    page_texts = []

    with pymupdf.open(path, filetype="pdf") as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("Expected an unlocked PDF")
        if set(details) != set(range(1, len(document)+1)) or len(details) != len(page_details):
            raise ValueError("Page plan does not match PDF pages")

        for number, page in enumerate(document, 1):
            detail = details[number]
            text = ""

            if detail.method == "native":
                text = page.get_text()
                if not text_quality(text)[0]:
                    detail.method = "ocr"
                    detail.reasons.append("native_quality_failed_ocr_fallback")

            if detail.method == "ocr":
                if engine is None:
                    engine = create_ocr_engine()
                import numpy as np
                pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
                image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                image = image[:, :, ::-1].copy()
                results = engine.ocr(image, cls=False)
                lines = []
                for line in results:
                    for word_info in line:
                        lines.append(word_info[1][0])
                text = "\n".join(lines)
                if not text_quality(text)[0]:
                    detail.method = "review"
                    detail.reasons.append("ocr_produced_no_usable_text")
                    text = ""

            page_texts.append(text)

    return {
        "source": str(path),
        "raw_text": "\n\n".join(page_texts),
        "text_by_page": page_texts,
    }
