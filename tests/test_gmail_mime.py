"""Unit tests for MIME -> email dict mapping. All fixtures are built
in-memory with email.message.EmailMessage -- no network, no filesystem."""
from email.message import EmailMessage

from averis_email.gmail_mime import parse_message, sanitize_filename
from averis_email.stages.classification import find_si_bl


def _raw(msg):
    return msg.as_bytes()


def test_plain_text_message_no_attachments():
    msg = EmailMessage()
    msg['From'] = 'Shipper <shipper@example.com>'
    msg['To'] = 'ops@example.com'
    msg['Subject'] = 'Please confirm booking'
    msg['Date'] = 'Mon, 21 Sep 2026 10:00:00 +0000'
    msg.set_content('Can you confirm the booking for next week?')

    record, attachments = parse_message(_raw(msg), uid=42, uidvalidity=1001)

    assert record['email_id'] == 'gmail_1001_42'
    assert record['from'] == 'Shipper <shipper@example.com>'
    assert record['subject'] == 'Please confirm booking'
    assert record['body'] == 'Can you confirm the booking for next week?'
    assert record['received_at'] == '2026-09-21T10:00:00+00:00'
    assert record['gmail_uid'] == 42
    assert record['gmail_uidvalidity'] == 1001
    assert record['source'] == 'gmail'
    assert attachments == []


def test_multipart_alternative_prefers_plain_text():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'Alt body'
    msg.set_content('Plain version')
    msg.add_alternative('<html><body><p>HTML version</p></body></html>', subtype='html')

    record, _ = parse_message(_raw(msg), uid=1, uidvalidity=1)
    assert record['body'] == 'Plain version'


def test_html_only_body_is_stripped():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'HTML only'
    msg.set_content('<html><body><p>Hello <b>world</b></p></body></html>', subtype='html')

    record, _ = parse_message(_raw(msg), uid=2, uidvalidity=1)
    assert 'Hello' in record['body']
    assert 'world' in record['body']
    assert '<' not in record['body']


def test_encoded_subject_is_decoded():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = '=?UTF-8?B?U2hpcHBpbmcgSW5zdHJ1Y3Rpb25z?='  # "Shipping Instructions"
    msg.set_content('body')

    record, _ = parse_message(_raw(msg), uid=3, uidvalidity=1)
    assert record['subject'] == 'Shipping Instructions'


def test_attachments_are_extracted_and_findable_as_si_bl():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'Docs attached'
    msg.set_content('See attached.')
    msg.add_attachment(b'%PDF-fake-si', maintype='application', subtype='pdf', filename='SI_2026.pdf')
    msg.add_attachment(b'%PDF-fake-bl', maintype='application', subtype='pdf', filename='draft_BL_2026.pdf')

    record, attachments = parse_message(_raw(msg), uid=4, uidvalidity=1)
    names = [name for name, _ in attachments]
    assert names == ['SI_2026.pdf', 'draft_BL_2026.pdf']
    assert dict(attachments)['SI_2026.pdf'] == b'%PDF-fake-si'

    # The filename-based SI/BL resolver must still work on sanitized names.
    email_with_paths = {**record, 'attachments': [f'gmail/{record["email_id"]}/{n}' for n in names]}
    resolution = find_si_bl(email_with_paths)
    assert resolution.si_path == f'gmail/{record["email_id"]}/SI_2026.pdf'
    assert resolution.bl_path == f'gmail/{record["email_id"]}/draft_BL_2026.pdf'


def test_non_ascii_attachment_filename_is_decoded_and_sanitized():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'Docs'
    msg.set_content('body')
    msg.add_attachment(b'data', maintype='application', subtype='pdf', filename='fattura Ünïcödé.pdf')

    _, attachments = parse_message(_raw(msg), uid=5, uidvalidity=1)
    assert len(attachments) == 1
    name = attachments[0][0]
    from averis_email.manual_store import FILENAME_RE
    assert FILENAME_RE.match(name)
    assert name.endswith('.pdf')


def test_duplicate_attachment_names_are_deduplicated():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'Dupes'
    msg.set_content('body')
    msg.add_attachment(b'one', maintype='application', subtype='pdf', filename='SI.pdf')
    msg.add_attachment(b'two', maintype='application', subtype='pdf', filename='SI.pdf')

    _, attachments = parse_message(_raw(msg), uid=6, uidvalidity=1)
    names = [n for n, _ in attachments]
    assert len(names) == len(set(n.lower() for n in names)) == 2
    assert names[0] != names[1]


def test_no_date_header_falls_back_to_now():
    msg = EmailMessage()
    msg['From'] = 'a@example.com'
    msg['To'] = 'b@example.com'
    msg['Subject'] = 'No date'
    msg.set_content('body')

    record, _ = parse_message(_raw(msg), uid=7, uidvalidity=1)
    assert record['received_at']  # some ISO timestamp, not blank/None


def test_sanitize_filename_strips_path_separators_and_control_chars():
    seen = set()
    name = sanitize_filename('../../etc/passwd', seen)
    assert '/' not in name and '..' not in name.replace('.', '')


def test_sanitize_filename_handles_empty_input():
    seen = set()
    name = sanitize_filename('', seen)
    assert name == 'attachment'
