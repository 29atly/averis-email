import tempfile
import unittest
from pathlib import Path

from docx import Document
from openpyxl import Workbook

from averis_email.extraction_pipeline import extract_file


class StructuredExtractionTests(unittest.TestCase):
    def setUp(self):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        self.root = Path(folder.name)

    def test_text_is_returned_verbatim(self):
        content = ('Heading\nShipper (Principal or Seller): Example Ltd\n'
                   '  123 Main St\n\nSingapore\nConsignee:\nNotify Party: Receiver\n')
        path = self.root / 'input.TXT'
        path.write_text(content, encoding='utf-8-sig')
        result = extract_file(path)
        self.assertEqual(result.status, 'EXTRACTED')
        self.assertEqual(result.extraction['raw_text'], content)
        self.assertNotIn('fields', result.extraction)

    def test_utf16(self):
        path = self.root / 'input.txt'
        path.write_text('Shipper： 公司', encoding='utf-16')
        self.assertEqual(extract_file(path).extraction['raw_text'], 'Shipper： 公司')

    def test_word_paragraphs_and_tables_in_document_order(self):
        doc = Document()
        doc.add_paragraph('B/L NO.(提单号): ABC123')
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'Shipper (Principal or Seller) (发货人)'
        table.cell(0, 1).text = 'Company\nAddress'
        table.cell(1, 0).text = 'Notify Party/Intermediate Consignee (通知人)'
        table.cell(1, 1).text = 'Receiver'
        doc.add_paragraph('Gross Wt (kgs) (毛重 KGS): 123 KG')
        for extension in ('docx', 'docs'):
            path = self.root / ('input.' + extension)
            doc.save(path)
            result = extract_file(path)
            self.assertEqual(result.status, 'EXTRACTED', result.message)
            self.assertEqual(result.extraction['raw_text'], '\n'.join([
                'B/L NO.(提单号): ABC123',
                'Shipper (Principal or Seller) (发货人)\tCompany\nAddress',
                'Notify Party/Intermediate Consignee (通知人)\tReceiver',
                'Gross Wt (kgs) (毛重 KGS): 123 KG',
            ]))

    def test_spreadsheet_rows_are_tab_separated_per_sheet(self):
        book = Workbook()
        sheet = book.active
        sheet.append(['Shipper:', 'Company', 'Unrelated'])
        sheet.append([None, None, None])
        sheet.append(['Gross Weight', 0])
        other = book.create_sheet('Second')
        other.append(['Consignee', 'Receiver'])
        path = self.root / 'input.XLSX'
        book.save(path)
        book.close()
        result = extract_file(path)
        self.assertEqual(result.status, 'EXTRACTED', result.message)
        self.assertEqual(result.extraction['raw_text'].splitlines(), [
            'Sheet: Sheet',
            'Shipper:\tCompany\tUnrelated',
            'Gross Weight\t0',
            'Sheet: Second',
            'Consignee\tReceiver',
        ])

    def test_corrupt_office_files(self):
        for extension in ('xlsx', 'docx', 'docs'):
            path = self.root / ('input.' + extension)
            path.write_text('not an Office document')
            self.assertEqual(extract_file(path).status, 'ERROR')
