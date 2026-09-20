"""Intent-labeled regression cases; no organizer answer key is used."""
import unittest
from averis_email.stages.classification import classify_email, find_si_bl

class EmailIntelligenceTests(unittest.TestCase):
    def test_intents(self):
        """Verify that common email messages are assigned the correct intent."""
        cases = [
            ('Check documents', 'Please verify the BL against the SI.', 'BL_COMPARISON'),
            ('Request', 'Please send the draft BL for checking.', 'BL_COMPARISON'),
            ('New shipment', 'Please prepare the shipping instruction.', 'SI_REQUEST'),
            ('REQUEST SI', 'Please find Shipping instruction for order 42.', 'SI_REQUEST'),
            ('Charges', 'Query on invoice 123: please advise the breakdown.', 'INVOICE_QUERY'),
            ('Update', 'The vessel arrived on schedule.', 'GENERAL'),
            ('Winner', 'You won the lottery. Claim your prize.', 'SPAM'),
            ('Account', 'Your mailbox has exceeded its storage limit.', 'SPAM'),
            ('REQUEST SI', 'Kindly find the daily berthing report attached.', 'GENERAL'),
            ('Invoice 42', 'Please check the draft BL against the SI.', 'BL_COMPARISON'),
            ('Draft BL', 'Query on invoice 42: is THC included?', 'INVOICE_QUERY'),
            ('Daily', 'Reminder: Please submit SI & AED for all pending shipments.', 'GENERAL'),
            ('SI - ABC - DIRECT', '', 'SI_REQUEST'),
        ]
        for subject, body, expected in cases:
            with self.subTest(subject=subject, body=body):
                self.assertEqual(classify_email(dict(subject=subject, body=body)), expected)

    def test_attachment_presence_is_not_intent(self):
        """Verify that attachment filenames do not determine email intent."""
        for subject, paths, expected in [('Invoice query', ['invoice.pdf'], 'INVOICE_QUERY'),
                                        ('Team photo', ['photo.jpg'], 'GENERAL'),
                                        ('Check draft BL', [], 'BL_COMPARISON')]:
            with self.subTest(subject=subject):
                self.assertEqual(classify_email(dict(subject=subject, attachments=paths)), expected)

    def test_history(self):
        """Verify that quoted or previous email history is ignored during classification."""
        for boundary in ['From: someone', 'On Monday someone wrote:', '-----Original Message-----', 'Best Regards,']:
            with self.subTest(boundary=boundary):
                self.assertEqual(classify_email(dict(subject='Update', body='The vessel arrived.\n' + boundary + '\nPlease check draft BL.')), 'GENERAL')

    def test_empty(self):
        """Verify that quoted or previous email history is ignored during classification."""
        self.assertEqual(classify_email({}), 'GENERAL')
        self.assertEqual(classify_email(dict(subject=None, body=None)), 'GENERAL')

    def test_new_si_with_future_bl_and_invoice_mentions(self):
        """Verify that a new SI request remains SI_REQUEST despite BL and invoice mentions."""
        body = 'Please find Shipping instruction for order 42. Documents Required: Original invoice, Original BL. Please revert with draft BL once available.'
        self.assertEqual(classify_email(dict(body=body)), 'SI_REQUEST')

    def test_additional_spam_signals(self):
        """Verify that additional spam patterns are correctly detected."""
        for body in ['Your email was selected in our monthly draw. Claim your gift card.',
                     'Your package could not be delivered due to unpaid customs fee of $2.99.']:
            with self.subTest(body=body):
                self.assertEqual(classify_email(dict(body=body)), 'SPAM')

    def test_formats_and_paths(self):
        """Verify that SI and BL attachments are correctly identified across filename formats and paths."""
        for si, bl in [('attachments/email_004_SI.txt', 'attachments/email_004_BL.txt'),
                       ('Folder/ShippingInstruction_102.xlsx', 'Folder/DraftBL_102.docx'),
                       ('Folder/SI_23991.PDF', 'Folder/Bill of Lading.pdf'),
                       ('Folder\\Shipping Instructions.docx', 'Folder\\B-L.pdf')]:
            with self.subTest(si=si):
                result = find_si_bl(dict(attachments=['invoice.pdf', bl, si]))
                self.assertEqual((result.si_path, result.bl_path), (si, bl))
                self.assertFalse(result.review_required)

    def test_missing_or_ambiguous(self):
        """Verify that missing or ambiguous SI/BL attachments require human review."""
        for paths in [[], ['SI.pdf'], ['BL.pdf'], ['SI.pdf', 'BL_v1.pdf', 'BL_v2.pdf'], ['SI_BL.pdf']]:
            with self.subTest(paths=paths):
                result = find_si_bl(dict(attachments=paths))
                self.assertTrue(result.review_required)
                self.assertEqual(result.review_reason, 'missing_attachment')
                self.assertTrue(result.warnings)

    def test_preserve_unique_candidate(self):
        """Verify that a unique SI is preserved even when the BL is ambiguous."""
        result = find_si_bl(dict(attachments=['SI.pdf', 'BL_v1.pdf', 'BL_v2.pdf']))
        self.assertEqual(result.si_path, 'SI.pdf')
        self.assertIsNone(result.bl_path)

    def test_duplicates(self):
        """Verify that duplicate attachment paths do not create false ambiguity."""
        self.assertFalse(find_si_bl(dict(attachments=['SI.pdf', 'SI.pdf', 'BL.pdf'])).review_required)

    def test_no_substring_or_parent_matching(self):
        """Verify that filenames are matched by document role rather than arbitrary path substrings."""
        result = find_si_bl(dict(attachments=['SI/file.pdf', 'BL/file.pdf', 'possible.pdf', 'visible.pdf']))
        self.assertIsNone(result.si_path)
        self.assertIsNone(result.bl_path)

    def test_invalid_attachment_input(self):
        """Verify that invalid attachment inputs safely trigger human review."""
        for paths in ['SI.pdf', [None, 12, ''], None]:
            with self.subTest(paths=paths):
                self.assertTrue(find_si_bl(dict(attachments=paths)).review_required)

if __name__ == '__main__':
    unittest.main()
