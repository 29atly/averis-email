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

    def test_bank_proposal_scam(self):
        """Regression for participant email_226, labeled by manual review."""
        email = {
            'subject': 'Exclusive offer: 90% OFF premium logistics software this week only',
            'body': 'Hello Dear, I am a bank officer with an urgent business proposal involving USD 4.5 million. Please reply with your bank details to proceed.',
        }
        self.assertEqual(classify_email(email), 'SPAM')

    def test_legitimate_bank_correspondence(self):
        """Bank details alone, or a proposal alone, must not trigger spam."""
        cases = [
            ('Invoice payment', 'Please reply with your bank details for payment of invoice 42.', 'INVOICE_QUERY'),
            ('Bank meeting', 'Our bank officer will attend the meeting tomorrow.', 'GENERAL'),
            ('Business proposal', 'Please review our business proposal involving USD 4.5 million for warehouse construction.', 'GENERAL'),
            ('Invoice update', 'Our bank officer confirmed payment of invoice 42.', 'INVOICE_QUERY'),
        ]
        for subject, body, expected in cases:
            with self.subTest(subject=subject):
                self.assertEqual(classify_email(dict(subject=subject, body=body)), expected)

    def test_quoted_bank_scam_does_not_override_current_invoice(self):
        body = ('Please clarify invoice 42.\nFrom: unknown sender\n'
                'I am a bank officer with an urgent business proposal involving USD 4.5 million. '
                'Please reply with your bank details to proceed.')
        self.assertEqual(classify_email(dict(body=body)), 'INVOICE_QUERY')

    def test_billing_completion_notices(self):
        cases = [
            'This is an automated notification. The India HSS SD Billing Process for MARCOPOLO 810 V.BS005 has completed successfully. No action required.',
            'Automated notification: billing process for Vessel A completed successfully. No further action is required.',
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(classify_email(dict(subject='Billing update', body=body)), 'GENERAL')

    def test_actionable_billing_is_not_completion_only(self):
        cases = [
            'Automated notification: billing process failed. Please retry.',
            'Billing process completed. Invoice 42 is disputed. Please investigate.',
            'Billing process completed successfully. No action required for this run. However, GR is missing for invoice 42.',
            'Billing process completed successfully. No action required for this run. Please pay invoice 42.',
            'Billing process has not completed successfully. No action required until support responds.',
            'Could you confirm whether the billing process completed successfully? No action required until confirmed.',
            'Invoice 42 has the wrong amount. Please correct it.',
        ]
        for body in cases:
            with self.subTest(body=body):
                self.assertEqual(classify_email(dict(body=body)), 'INVOICE_QUERY')

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
