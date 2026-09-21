"""IMAP access to a Gmail mailbox: login, mailbox status, and fetching new
messages by UID. Pure IMAP transport only -- MIME parsing lives in
gmail_mime.py, disk persistence in gmail_store.py, and scheduling/backoff
in the poller (gmail_poller.py). Kept read-only throughout: every fetch
selects INBOX with EXAMINE (readonly=True) so ingestion can never mark a
message \\Seen or otherwise mutate a mailbox a human might also be reading.
"""
import imaplib
import re
import socket

HOST = 'imap.gmail.com'
PORT = 993

# A poll fetches at most this many messages, so one burst of mail can't
# stall the 60s poller loop indefinitely; the rest are picked up next cycle.
MAX_MESSAGES_PER_POLL = 20
# Skip (not crash on) anything this large -- rare for shipping documents,
# but a single huge attachment shouldn't be able to wedge ingestion.
MAX_MESSAGE_BYTES = 30 * 1024 * 1024

_UIDVALIDITY_RE = re.compile(rb'UIDVALIDITY (\d+)')
_UIDNEXT_RE = re.compile(rb'UIDNEXT (\d+)')
_SIZE_ENTRY_RE = re.compile(rb'UID (\d+) RFC822\.SIZE (\d+)')


class GmailAuthError(Exception):
    """Login rejected: bad address/app password, IMAP disabled, or 2-Step
    Verification not enabled on the account (app passwords require it)."""


class GmailConnectionError(Exception):
    """Network/timeout reaching Gmail -- distinct from bad credentials so
    callers can back off instead of surfacing it as a credentials error."""


def _logout(conn):
    try:
        conn.logout()
    except Exception:
        pass


def connect(address, password, timeout=10):
    """Log in and return an authenticated IMAP4_SSL connection. Raises
    GmailAuthError or GmailConnectionError; caller owns logout()."""
    try:
        conn = imaplib.IMAP4_SSL(HOST, PORT, timeout=timeout)
    except (OSError, socket.timeout) as exc:
        raise GmailConnectionError(f'Could not reach {HOST}: {exc}') from exc
    try:
        conn.login(address, password)
    except imaplib.IMAP4.error as exc:
        _logout(conn)
        raise GmailAuthError(str(exc)) from exc
    return conn


def test_login(address, password, timeout=10):
    """Log in and immediately log out. Raises GmailAuthError or
    GmailConnectionError; returns nothing on success."""
    conn = connect(address, password, timeout=timeout)
    _logout(conn)


def mailbox_status(address, password, timeout=10):
    """Return (uidvalidity, uidnext) for INBOX without fetching any
    messages. Used to baseline a newly enabled mailbox to its current tip,
    and to detect a UIDVALIDITY change (the server reassigned UIDs, e.g.
    after the mailbox was recreated) between polls."""
    conn = connect(address, password, timeout=timeout)
    try:
        typ, data = conn.status('INBOX', '(UIDVALIDITY UIDNEXT)')
        if typ != 'OK' or not data or not data[0]:
            raise GmailConnectionError('Could not read INBOX status')
        raw = data[0]
        uidvalidity = _UIDVALIDITY_RE.search(raw)
        uidnext = _UIDNEXT_RE.search(raw)
        if not uidvalidity or not uidnext:
            raise GmailConnectionError(f'Unexpected STATUS response: {raw!r}')
        return int(uidvalidity.group(1)), int(uidnext.group(1))
    finally:
        _logout(conn)


def fetch_since(address, password, since_uid, timeout=30):
    """Log in and fetch RFC822 bytes for every INBOX message with
    UID > since_uid, ascending, capped at MAX_MESSAGES_PER_POLL.

    Returns (uidvalidity, messages): messages is a list of
    (uid, raw_bytes_or_None, skipped_reason_or_None). A message over
    MAX_MESSAGE_BYTES comes back with raw_bytes=None and a reason, but its
    uid is still included so the caller advances the checkpoint past it
    instead of re-fetching (and re-skipping) it forever.
    """
    conn = connect(address, password, timeout=timeout)
    try:
        typ, status_data = conn.status('INBOX', '(UIDVALIDITY)')
        if typ != 'OK' or not status_data or not status_data[0]:
            raise GmailConnectionError('Could not read INBOX status')
        match = _UIDVALIDITY_RE.search(status_data[0])
        if not match:
            raise GmailConnectionError(f'Unexpected STATUS response: {status_data[0]!r}')
        uidvalidity = int(match.group(1))

        typ, _data = conn.select('INBOX', readonly=True)
        if typ != 'OK':
            raise GmailConnectionError('Could not select INBOX')

        typ, search_data = conn.uid('search', None, f'UID {since_uid + 1}:*')
        if typ != 'OK':
            raise GmailConnectionError('IMAP UID SEARCH failed')
        found = {int(u) for u in (search_data[0] or b'').split()}
        # RFC 3501: '*' in a UID range matches the highest UID in the
        # mailbox even when it falls below the requested range -- filter
        # that stray hit back out rather than re-ingesting old mail.
        uids = sorted(u for u in found if u > since_uid)[:MAX_MESSAGES_PER_POLL]
        if not uids:
            return uidvalidity, []

        typ, size_data = conn.uid('fetch', ','.join(str(u) for u in uids), '(RFC822.SIZE)')
        if typ != 'OK':
            raise GmailConnectionError('IMAP FETCH (size) failed')
        sizes = {}
        for item in size_data:
            raw = item[0] if isinstance(item, tuple) else item
            match = _SIZE_ENTRY_RE.search(raw or b'')
            if match:
                sizes[int(match.group(1))] = int(match.group(2))

        messages = []
        for uid in uids:
            size = sizes.get(uid)
            if size is not None and size > MAX_MESSAGE_BYTES:
                messages.append((uid, None, f'Message too large to ingest ({size} bytes)'))
                continue
            typ, msg_data = conn.uid('fetch', str(uid), '(RFC822)')
            if typ != 'OK':
                messages.append((uid, None, 'IMAP FETCH failed'))
                continue
            raw_bytes = next((part[1] for part in msg_data if isinstance(part, tuple)), None)
            if raw_bytes is None:
                messages.append((uid, None, 'Empty IMAP FETCH response'))
                continue
            messages.append((uid, raw_bytes, None))
        return uidvalidity, messages
    finally:
        _logout(conn)
