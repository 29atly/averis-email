import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from averis_email.extraction_pipeline import execute_plan, extract_file, inspect_document
from averis_email.extraction_pipeline.ocr import extract_ocr_pdf


class FakeOCR:
    def __init__(self, score=0.99):
        self.calls = 0
        self.score = score

    def predict(self, image, **kwargs):
        self.calls += 1
        return [{"rec_texts": ["Shipper: Scanned Company"], "rec_scores": [self.score],
                 "rec_boxes": [[20, 20, 500, 50]]}]


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'input.pdf'

    def pdf(self, mixed=False):
        with pymupdf.open() as doc:
            if mixed:
                doc.new_page().insert_text((20, 40), 'Shipper: Native Company')
            page = doc.new_page()
            with pymupdf.open() as source:
                source.new_page().insert_text((20, 40), 'Shipper: Scanned Company')
                page.insert_image(page.rect, stream=source[0].get_pixmap().tobytes('png'))
            doc.save(self.path)

    def test_mixed_pages_only_ocr_scan_and_inspect_once(self):
        self.pdf(mixed=True)
        engine = FakeOCR()
        with (patch('averis_email.extraction_pipeline.ocr.create_ocr_engine', return_value=engine),
              patch('averis_email.extraction_pipeline.ocr.inspect_pdf', side_effect=AssertionError('reinspection'))):
            result = extract_file(self.path)
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertEqual(engine.calls, 1)
        self.assertEqual([p.method for p in result.pages], ['native', 'ocr'])
        self.assertIn('Native Company', result.extraction['text_by_page'][0])
        self.assertEqual(result.extraction['text_by_page'][1], 'Shipper: Scanned Company')

    def test_low_confidence_requires_review(self):
        self.pdf()
        with patch('averis_email.extraction_pipeline.ocr.create_ocr_engine', return_value=FakeOCR(.1)):
            result = extract_file(self.path)
        self.assertEqual(result.status, 'NEEDS_REVIEW')
        self.assertEqual(result.pages[0].method, 'review')

    def test_native_failure_falls_back_once_and_preserves_input_plan(self):
        self.pdf()
        plan = inspect_document(self.path)
        # Simulate a native decision whose text fails execution-time validation.
        plan.pages[0].method = 'native'
        engine = FakeOCR()
        with patch('averis_email.extraction_pipeline.ocr.create_ocr_engine', return_value=engine):
            result = execute_plan(self.path, plan)
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertEqual(engine.calls, 1)
        self.assertEqual(plan.pages[0].method, 'native')
        self.assertEqual(result.pages[0].method, 'ocr')
        self.assertIn('native_quality_failed_ocr_fallback', result.pages[0].reasons)

    def test_changed_file_and_missing_handler(self):
        self.pdf()
        plan = inspect_document(self.path)
        self.assertEqual(execute_plan(self.path, plan, {}).status, 'NOT_IMPLEMENTED')
        self.path.write_bytes(b'changed')
        result = execute_plan(self.path, plan, {'ocr': lambda *args: self.fail('stale plan executed')})
        self.assertEqual(result.status, 'ERROR')
        self.assertIn('changed', result.message)

    def test_registered_structured_handler(self):
        self.path = self.path.with_suffix('.txt')
        self.path.write_text('Shipper: Example')
        result = extract_file(self.path, {'txt': lambda path, plan: {'text': path.read_text()}})
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertEqual(result.extraction['text'], 'Shipper: Example')

    def test_renamed_native_extraction_does_not_load_ocr(self):
        with pymupdf.open() as doc:
            doc.new_page().insert_text((20, 40), 'Shipper: Native Company')
            doc.save(self.path)
        renamed = self.path.with_suffix('.bin')
        self.path.rename(renamed)
        with patch('averis_email.extraction_pipeline.ocr.create_ocr_engine', side_effect=AssertionError('OCR loaded')):
            result = extract_file(renamed)
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertTrue(result.plan.extension_mismatch)

    def test_missing_ocr_dependency_is_explicit_error(self):
        self.pdf()
        with patch('averis_email.extraction_pipeline.ocr.create_ocr_engine', side_effect=RuntimeError('Install OCR dependencies')):
            result = extract_file(self.path)
        self.assertEqual(result.status, 'ERROR')
        self.assertIn('Install OCR', result.message)
