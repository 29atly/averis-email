"""Execute a PDF page plan with native words or one PaddleOCR pass per page."""
from collections.abc import Mapping
from pathlib import Path
import re

import pymupdf

from averis_email.config.keywords import KEYWORD_ALIASES
from averis_email.stages.pdf_extraction import Word, build_extraction_result, extract_page, lines
from .detection import inspect_pdf, text_quality
from .models import PdfPage


def create_ocr_engine():
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise RuntimeError("Install OCR dependencies with pip install -e '.[ocr]'") from exc
    return PaddleOCR(lang="en", use_doc_orientation_classify=False,
                     use_doc_unwarping=False, use_textline_orientation=False)


def _page_words_from_ocr(page, engine, dpi, min_confidence):
    import numpy as np

    pix = page.get_pixmap(dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
    image = image[:, :, ::-1].copy()  # Paddle's ndarray input uses BGR.
    sx, sy = page.rect.width / pix.width, page.rect.height / pix.height
    words = []
    for result in engine.predict(image, text_rec_score_thresh=min_confidence):
        payload = result if isinstance(result, Mapping) else result.json
        payload = payload() if callable(payload) else payload
        payload = payload.get("res", payload)
        texts, scores = payload.get("rec_texts", []), payload.get("rec_scores", [])
        boxes = payload.get("rec_boxes")
        if boxes is None:
            boxes = payload.get("rec_polys", [])
        for index, (text, box) in enumerate(zip(texts, boxes)):
            if index >= len(scores) or float(scores[index]) < min_confidence:
                continue
            box = box.tolist() if hasattr(box, "tolist") else box
            if isinstance(box[0], (list, tuple)):
                x0, x1 = min(p[0] for p in box), max(p[0] for p in box)
                y0, y1 = min(p[1] for p in box), max(p[1] for p in box)
            else:
                x0, y0, x1, y1 = box
            # Paddle reports line boxes. Approximate word positions within each
            # line to reuse the native coordinate-based keyword mapper.
            text = str(text)
            for match in re.finditer(r"\S+", text):
                words.append(Word((x0 + (x1-x0)*match.start()/len(text))*sx, y0*sy,
                                  (x0 + (x1-x0)*match.end()/len(text))*sx, y1*sy, match.group()))
    return words


def extract_ocr_pdf(path: str | Path, aliases=KEYWORD_ALIASES, *, engine=None,
                    dpi: int = 200, min_confidence: float = 0.5,
                    page_details: list[PdfPage] | None = None) -> dict:
    if dpi <= 0:
        raise ValueError("OCR DPI must be positive")
    if not 0 <= min_confidence <= 1:
        raise ValueError("OCR confidence must be between zero and one")
    path = Path(path)
    if page_details is None:
        _, page_details = inspect_pdf(path)
    details = {detail.page: detail for detail in page_details}
    occurrences, empty_pages, page_texts = [], [], []
    with pymupdf.open(path, filetype="pdf") as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("Expected an unlocked PDF")
        if set(details) != set(range(1, len(document)+1)) or len(details) != len(page_details):
            raise ValueError("Page plan does not match PDF pages")
        for number, page in enumerate(document, 1):
            detail = details[number]
            words = []
            if detail.method == "native":
                words = [Word(*w[:5]) for w in page.get_text("words")]
                if not text_quality(" ".join(w.text for w in words))[0]:
                    detail.method = "ocr"
                    detail.reasons.append("native_quality_failed_ocr_fallback")
            if detail.method == "ocr":
                if engine is None:
                    engine = create_ocr_engine()
                words = _page_words_from_ocr(page, engine, dpi, min_confidence)
                if not text_quality(" ".join(w.text for w in words))[0]:
                    detail.method = "review"
                    detail.reasons.append("ocr_produced_no_usable_text")
                    words = []
            page_texts.append("\n".join(" ".join(w.text for w in row) for row in lines(words)))
            if not words:
                empty_pages.append(number)
            occurrences.extend(extract_page(words, page.rect.height, number, aliases))
    return build_extraction_result(path, occurrences, empty_pages, aliases, raw_text="\n\n".join(page_texts))
