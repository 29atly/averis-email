"""Tests for PaddleOCR adaptation without downloading inference models."""

import tempfile
import unittest
from pathlib import Path

import pymupdf

from averis_email.extraction_pipeline.ocr import extract_ocr_pdf


class FakeResult:
    def __init__(self, payload):
        self.json = {"res": payload}


class FakePaddleOCR:
    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def predict(self, image, **kwargs):
        self.calls.append((image.shape, kwargs))
        lines = self.pages.pop(0)
        width = image.shape[1]
        return [FakeResult({
            "rec_texts": [line[0] for line in lines],
            "rec_scores": [line[1] for line in lines],
            "rec_boxes": [
                [
                    20,
                    20 + index * 80,
                    min(width - 20, 20 + len(line[0]) * 12),
                    50 + index * 80,
                ]
                for index, line in enumerate(lines)
            ],
        })]


class OCRExtractionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "scan.pdf"

    @staticmethod
    def _insert_scan(page):
        with pymupdf.open() as source:
            source_page = source.new_page()
            source_page.insert_text((20, 40), "Rasterized document")
            png = source_page.get_pixmap().tobytes("png")
        page.insert_image(page.rect, stream=png)

    def _create_pdf(self, mixed=False):
        with pymupdf.open() as document:
            if mixed:
                page = document.new_page()
                page.insert_text((20, 40), "SHIPPER:")
                page.insert_text((150, 40), "Native Company")
            self._insert_scan(document.new_page())
            document.save(self.path)

    def test_scanned_pdf_returns_recognized_lines_as_raw_text(self):
        self._create_pdf()
        engine = FakePaddleOCR([[
            ("Shipper: Scanned Company", 0.99),
            ("Port of Loading: Singapore", 0.98),
        ]])

        result = extract_ocr_pdf(self.path, engine=engine)

        self.assertEqual(result["raw_text"], "Shipper: Scanned Company\nPort of Loading: Singapore")
        self.assertEqual(result["text_by_page"], [result["raw_text"]])
        self.assertEqual(result["pages_without_text"], [])
        self.assertNotIn("fields", result)
        self.assertEqual(engine.calls[0][1]["text_rec_score_thresh"], 0.5)
        self.assertEqual(engine.calls[0][0][2], 3)

    def test_mixed_pdf_only_sends_scanned_pages_to_ocr(self):
        self._create_pdf(mixed=True)
        engine = FakePaddleOCR([[["Port of Discharge: Rotterdam", 0.99]]])

        result = extract_ocr_pdf(self.path, engine=engine)

        self.assertEqual(len(engine.calls), 1)
        self.assertEqual(len(result["text_by_page"]), 2)
        self.assertIn("Native Company", result["text_by_page"][0])
        self.assertEqual(result["text_by_page"][1], "Port of Discharge: Rotterdam")

    def test_low_confidence_text_is_ignored_and_page_is_reported_empty(self):
        self._create_pdf()
        engine = FakePaddleOCR([[["Shipper: Unreliable Company", 0.20]]])

        result = extract_ocr_pdf(self.path, engine=engine, min_confidence=0.5)

        self.assertEqual(result["raw_text"], "")
        self.assertEqual(result["pages_without_text"], [1])

    def test_ocr_options_are_validated(self):
        with self.assertRaisesRegex(ValueError, "DPI"):
            extract_ocr_pdf(self.path, engine=FakePaddleOCR([]), dpi=0)
        with self.assertRaisesRegex(ValueError, "confidence"):
            extract_ocr_pdf(self.path, engine=FakePaddleOCR([]), min_confidence=2)


if __name__ == "__main__":
    unittest.main()
