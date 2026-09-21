"""Unit tests for the IMAP transport layer, against a hand-rolled fake that
mimics imaplib's real response shapes -- no network involved. See
https://docs.python.org/3/library/imaplib.html for the (typ, data) shapes
being reproduced: STATUS returns one bytes line, UID SEARCH returns one
space-separated bytes line, and UID FETCH of a literal (RFC822) returns a
list mixing (b'<meta>', b'<literal bytes>') tuples with plain closing bytes.
"""
import re

import imaplib

import pytest

from averis_email import gmail_client
from averis_email.gmail_client import GmailAuthError, GmailConnectionError, fetch_since, mailbox_status
# Aliased on import: a bare `test_login` name would make pytest collect
# Gmail's own login helper as a test case in this module.
from averis_email.gmail_client import test_login as gmail_test_login


class FakeConn:
    def __init__(self, messages, uidvalidity=1001, password='good-password', search_floor=None):
        """messages: {uid: raw_bytes}. search_floor mimics the RFC 3501
        quirk where 'UID N:*' returns the mailbox's highest UID even when
        it's below N, by injecting that stray hit into SEARCH results."""
        self.messages = messages
        self.uidvalidity = uidvalidity
        self.password = password
        self.search_floor = search_floor
        self.logged_out = False

    def login(self, address, password):
        if password != self.password:
            raise imaplib.IMAP4.error('AUTHENTICATIONFAILED')
        return 'OK', [b'Success']

    def status(self, mailbox, names):
        uidnext = max(self.messages, default=0) + 1
        return 'OK', [f'"INBOX" (UIDVALIDITY {self.uidvalidity} UIDNEXT {uidnext})'.encode()]

    def select(self, mailbox, readonly=False):
        assert readonly is True, 'ingestion must never SELECT for read-write'
        return 'OK', [str(len(self.messages)).encode()]

    def uid(self, command, *args):
        command = command.lower()
        if command == 'search':
            criteria = args[1]
            match = re.match(r'UID (\d+):\*', criteria)
            start = int(match.group(1))
            uids = {u for u in self.messages if u >= start}
            if not uids and self.search_floor is not None:
                uids = {self.search_floor}
            return 'OK', [' '.join(str(u) for u in sorted(uids)).encode()]
        if command == 'fetch':
            msg_set, item = args
            uids = [int(x) for x in msg_set.split(',')]
            if item == '(RFC822.SIZE)':
                data = [f'{u} (UID {u} RFC822.SIZE {len(self.messages[u])})'.encode()
                        for u in uids if u in self.messages]
                return 'OK', data
            if item == '(RFC822)':
                uid = uids[0]
                if uid not in self.messages:
                    return 'OK', [None]
                raw = self.messages[uid]
                return 'OK', [(f'{uid} (UID {uid} RFC822 {{{len(raw)}}}'.encode(), raw), b')']
        raise NotImplementedError(command)

    def logout(self):
        self.logged_out = True
        return 'BYE', [b'Logging out']


@pytest.fixture
def fake(monkeypatch):
    conn = FakeConn(messages={})

    def factory(host, port, timeout=None):
        assert host == gmail_client.HOST
        return conn

    monkeypatch.setattr(gmail_client.imaplib, 'IMAP4_SSL', factory)
    return conn


def test_mailbox_status_parses_uidvalidity_and_uidnext(fake):
    fake.messages = {5: b'raw-5'}
    uidvalidity, uidnext = mailbox_status('ops@example.com', 'good-password')
    assert uidvalidity == 1001
    assert uidnext == 6
    assert fake.logged_out is True


def test_test_login_success_logs_out(fake):
    gmail_test_login('ops@example.com', 'good-password')
    assert fake.logged_out is True


def test_bad_password_raises_auth_error(fake):
    with pytest.raises(GmailAuthError):
        gmail_test_login('ops@example.com', 'wrong-password')


def test_connection_failure_raises_connection_error(monkeypatch):
    def raises(host, port, timeout=None):
        raise OSError('network unreachable')
    monkeypatch.setattr(gmail_client.imaplib, 'IMAP4_SSL', raises)
    with pytest.raises(GmailConnectionError):
        gmail_test_login('ops@example.com', 'good-password')


def test_fetch_since_returns_only_newer_messages(fake):
    fake.messages = {1: b'old', 5: b'new-a', 6: b'new-b'}
    uidvalidity, messages = fetch_since('ops@example.com', 'good-password', since_uid=4)
    assert uidvalidity == 1001
    assert [(uid, raw, reason) for uid, raw, reason in messages] == [
        (5, b'new-a', None), (6, b'new-b', None)]


def test_fetch_since_returns_empty_when_no_new_mail(fake):
    fake.messages = {1: b'old'}
    uidvalidity, messages = fetch_since('ops@example.com', 'good-password', since_uid=99)
    assert messages == []
    assert uidvalidity == 1001


def test_fetch_since_filters_the_star_range_quirk(fake):
    """UID 100:* with nothing >= 100 still returns the mailbox's actual
    highest UID (here 3, injected via search_floor) -- fetch_since must not
    treat that as new mail."""
    fake.messages = {1: b'a', 3: b'c'}
    fake.search_floor = 3
    uidvalidity, messages = fetch_since('ops@example.com', 'good-password', since_uid=100)
    assert messages == []


def test_fetch_since_caps_messages_per_poll(fake, monkeypatch):
    monkeypatch.setattr(gmail_client, 'MAX_MESSAGES_PER_POLL', 2)
    fake.messages = {1: b'a', 2: b'b', 3: b'c', 4: b'd'}
    _, messages = fetch_since('ops@example.com', 'good-password', since_uid=0)
    assert [uid for uid, _, _ in messages] == [1, 2]


def test_fetch_since_skips_oversized_message_but_advances_past_it(fake, monkeypatch):
    monkeypatch.setattr(gmail_client, 'MAX_MESSAGE_BYTES', 10)
    fake.messages = {1: b'small', 2: b'this-one-is-too-large-to-ingest'}
    _, messages = fetch_since('ops@example.com', 'good-password', since_uid=0)
    assert messages[0] == (1, b'small', None)
    uid, raw, reason = messages[1]
    assert uid == 2 and raw is None and 'too large' in reason


def test_fetch_since_propagates_auth_error(fake):
    with pytest.raises(GmailAuthError):
        fetch_since('ops@example.com', 'wrong-password', since_uid=0)
