"""Regression tests for strict geometry and PDF word ingestion."""
import tempfile
import unittest
from pathlib import Path

import pymupdf

from averis_email.stages.extraction import Word, extract_page, extract_pdf


class ExtractionTests(unittest.TestCase):
    def test_multiline_strict_bounds_and_longest_alias(self):
        words = [Word(10, 10, 40, 20, 'Notify'), Word(45, 10, 70, 20, 'Party:'),
                 Word(80, 10, 120, 20, 'Company'), Word(80, 25, 120, 35, 'Address'),
                 Word(70, 25, 75, 35, 'excluded'),  # x0 equals label x1
                 Word(80, 35, 120, 45, 'boundary'),  # center equals next y0
                 Word(10, 40, 60, 50, 'Consignee'), Word(80, 40, 120, 50, 'Buyer')]
        hits = extract_page(words, 100)
        self.assertEqual([h['field'] for h in hits], ['notify_party', 'consignee'])
        self.assertEqual(hits[0]['value'], 'Company\nAddress')
        self.assertEqual(hits[1]['value'], 'Buyer')

    def test_three_word_window_and_custom_config(self):
        words = [Word(i*30, 10, i*30+25, 20, t) for i, t in enumerate(
            ['prefix', 'Port', 'of', 'Loading:', 'Singapore'])]
        self.assertEqual(extract_page(words, 100)[0]['value'], 'Singapore')
        custom = {'shipper': ('prefix',)}
        self.assertEqual(extract_page(words, 100, aliases=custom)[0]['field'], 'shipper')

    def test_same_row_and_below_header_follow_strict_rule(self):
        words = [Word(10, 10, 40, 20, 'Shipper'), Word(50, 10, 70, 20, 'Seller'),
                 Word(100, 10, 140, 20, 'Consignee'), Word(150, 10, 180, 20, 'Buyer')]
        self.assertIsNone(extract_page(words, 100)[0]['value'])
        self.assertIsNone(extract_page([Word(10, 10, 40, 20, 'Shipper'),
                                      Word(10, 30, 40, 40, 'Seller')], 100)[0]['value'])

    def test_pdf_pages_and_missing_fields(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'sample.pdf'
            with pymupdf.open() as doc:
                page = doc.new_page()
                page.insert_text((20, 40), 'SHIPPER:')
                page.insert_text((150, 40), 'Example Company')
                page.insert_text((150, 60), 'Example Address')
                doc.new_page()
                doc.save(path)
            result = extract_pdf(path)
        self.assertEqual(result['fields']['shipper'], 'Example Company\nExample Address')
        self.assertEqual(result['pages_without_text'], [2])
        self.assertIn('gross_weight_kg', result['missing_focus_fields'])


if __name__ == '__main__':
    unittest.main()
