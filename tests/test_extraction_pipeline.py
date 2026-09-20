import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pymupdf

from averis_email.extraction_pipeline import extract_file
from averis_email.stages.extraction import extract_pdf


class FileExtractionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / 'input.PDF'

    def create_pdf(self, kinds):
        with pymupdf.open() as document:
            for kind in kinds:
                page = document.new_page()
                if kind == 'text':
                    page.insert_text((20, 40), 'SHIPPER:')
                    page.insert_text((150, 40), 'Example Company')
                elif kind.startswith('scan'):
                    with pymupdf.open() as raster_source:
                        raster_page = raster_source.new_page()
                        raster_page.insert_text((20, 40), 'Shipper: Scanned Company')
                        png = raster_page.get_pixmap().tobytes('png')
                    page.insert_image(page.rect, stream=png)
                    if kind == 'scan_with_number':
                        page.insert_text((20, 800), '1')
            document.save(self.path)

    def test_epdf_connects_to_existing_extractor(self):
        self.create_pdf(['text'])
        result = extract_file(self.path)
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertEqual(result.pdf_type, 'epdf')
        self.assertEqual(result.route, 'pdf_extractor')
        self.assertEqual(result.extraction, extract_pdf(self.path))
        self.assertEqual(result.extraction['fields']['shipper'], 'Example Company')

    def test_scan_and_mixed_pdf_require_ocr(self):
        for kinds, expected in [(['scan'], 'scanned'), (['scan_with_number'], 'scanned'),
                                (['text', 'scan'], 'mixed')]:
            with self.subTest(kinds=kinds):
                self.create_pdf(kinds)
                with patch('averis_email.extraction_pipeline.handlers.extract_epdf') as digital:
                    result = extract_file(self.path)
                self.assertEqual(result.pdf_type, expected)
                self.assertEqual(result.route, 'ocr')
                self.assertEqual(result.status, 'NOT_IMPLEMENTED')
                self.assertIsNone(result.extraction)
                digital.assert_not_called()
                self.path.unlink()

    def test_blank_pages_do_not_turn_digital_pdf_into_scan(self):
        self.create_pdf(['text', 'blank'])
        result = extract_file(self.path)
        self.assertEqual(result.pdf_type, 'epdf')
        self.assertEqual(result.extraction['pages_without_text'], [2])

    def test_entirely_blank_pdf_requires_review(self):
        self.create_pdf(['blank'])
        result = extract_file(self.path)
        self.assertEqual(result.pdf_type, 'empty')
        self.assertEqual(result.status, 'NEEDS_REVIEW')

    def test_xlsx_and_txt_are_placeholders(self):
        for extension in ['XLSX', 'txt']:
            path = self.path.with_suffix('.' + extension)
            path.write_text('Placeholder input')
            result = extract_file(path)
            self.assertEqual(result.route, extension.lower())
            self.assertEqual(result.status, 'NOT_IMPLEMENTED')
            self.assertIsNone(result.extraction)

    def test_missing_directory_unsupported_and_corrupt_files(self):
        self.assertEqual(extract_file(self.path).status, 'ERROR')
        self.assertEqual(extract_file(self.path.parent).status, 'ERROR')
        unsupported = self.path.with_suffix('.docx')
        unsupported.write_text('No handler')
        self.assertEqual(extract_file(unsupported).file_type, 'unsupported')
        self.path.write_bytes(b'not a PDF')
        self.assertEqual(extract_file(self.path).status, 'ERROR')

    def test_encrypted_pdf_returns_error(self):
        with pymupdf.open() as document:
            document.new_page()
            document.save(self.path, encryption=pymupdf.PDF_ENCRYPT_AES_256,
                          owner_pw='owner', user_pw='password')
        result = extract_file(self.path)
        self.assertEqual(result.status, 'ERROR')
        self.assertIn('password', result.message)


if __name__ == '__main__':
    unittest.main()
