"""Maps a raw Gmail RFC822 message into the plain dict shape the pipeline and
UI already understand (email_id/from/to/subject/body/attachments).

Kept separate from gmail_client.py (which only speaks IMAP) and
gmail_store.py (which only speaks disk): pure functions here can be unit
tested against fixture .eml bytes with no network or filesystem involved.
"""
import re
from datetime import datetime, timezone
from email import message_from_bytes, policy
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser

from averis_email.manual_store import FILENAME_RE

MAX_SUBJECT_CHARS = 300
MAX_HEADER_CHARS = 300
MAX_CONTENT_CHARS = 100_000
CONTROL_CHARS_RE = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []

    def handle_data(self, data):
        self.parts.append(data)


def _strip_html(html):
    parser = _TextExtractor()
    try:
        parser.feed(html)
    except Exception:
        return html
    return re.sub(r'\n{3,}', '\n\n', ''.join(parser.parts)).strip()


def _decode_header(value):
    """RFC 2047 header decoding (=?UTF-8?B?...?= etc). Falls back to the
    raw value for a malformed header rather than raising."""
    if not value:
        return ''
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _clean(text, limit):
    return CONTROL_CHARS_RE.sub('', text or '')[:limit]


def _body(msg):
    """First text/plain part; falls back to text/html stripped of markup.
    Attachments are skipped even if mislabeled text/plain inline."""
    plain = html = None
    for part in msg.walk():
        if part.is_multipart() or part.get_content_disposition() == 'attachment':
            continue
        ctype = part.get_content_type()
        try:
            content = part.get_content()
        except Exception:
            continue
        if not isinstance(content, str):
            continue
        if ctype == 'text/plain' and plain is None:
            plain = content
        elif ctype == 'text/html' and html is None:
            html = content
    if plain is not None:
        return _clean(plain, MAX_CONTENT_CHARS).strip()
    if html is not None:
        return _clean(_strip_html(html), MAX_CONTENT_CHARS).strip()
    return ''


def _received_at(msg):
    date = msg.get('Date')
    if date:
        try:
            parsed = parsedate_to_datetime(date)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except (TypeError, ValueError):
            pass
    return datetime.now(timezone.utc).isoformat()


def sanitize_filename(name, seen_lower):
    """Map an attachment filename to one that passes manual_store's
    FILENAME_RE, preserving extension and word content (so SI/BL filename
    detection in stages/classification.py still matches) and de-duplicating
    against names already used in this message."""
    name = re.sub(r'[/\\]', '_', (name or '').strip()) or 'attachment'
    name = name[:120]
    stem, dot, suffix = name.rpartition('.')
    if not dot:
        stem, suffix = name, ''
    stem = re.sub(r'[^A-Za-z0-9 ._()\[\]-]', '_', stem).strip(' .') or 'attachment'
    suffix = re.sub(r'[^A-Za-z0-9]', '', suffix)
    base = f'{stem}.{suffix}' if suffix else stem

    candidate, n = base, 2
    while candidate.lower() in seen_lower or not FILENAME_RE.match(candidate):
        candidate = f'{stem} ({n}).{suffix}' if suffix else f'{stem} ({n})'
        n += 1
        if n > 999:  # pathological input -- stop looping, force a safe name
            candidate = f'attachment-{len(seen_lower)}.{suffix or "bin"}'
            break
    seen_lower.add(candidate.lower())
    return candidate


def parse_message(raw, uid, uidvalidity):
    """Returns (record, attachments): record is the email dict without an
    'attachments' key yet, attachments is [(filename, bytes), ...] still
    needing validate_filename/validate_content -- gmail_store.py owns the
    skip-vs-persist decision, so this function has no side effects and no
    knowledge of the allowed-extension policy."""
    msg = message_from_bytes(raw, policy=policy.default)
    seen_lower = set()
    attachments = []
    for part in msg.iter_attachments():
        try:
            content = part.get_content()
        except Exception:
            continue
        if isinstance(content, str):
            content = content.encode('utf-8', errors='replace')
        elif not isinstance(content, (bytes, bytearray)):
            continue
        name = sanitize_filename(_decode_header(part.get_filename()), seen_lower)
        attachments.append((name, bytes(content)))

    record = {
        'email_id': f'gmail_{uidvalidity}_{uid}',
        'from': _clean(_decode_header(msg.get('From')), MAX_HEADER_CHARS),
        'to': _clean(_decode_header(msg.get('To')), MAX_HEADER_CHARS),
        'subject': _clean(_decode_header(msg.get('Subject')), MAX_SUBJECT_CHARS),
        'body': _body(msg),
        'received_at': _received_at(msg),
        'source': 'gmail',
        'message_id': (msg.get('Message-ID') or '').strip()[:MAX_HEADER_CHARS],
        'gmail_uid': uid,
        'gmail_uidvalidity': uidvalidity,
    }
    return record, attachments
