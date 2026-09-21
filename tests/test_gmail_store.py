import json

import pytest

from averis_email.gmail_store import GmailStore


@pytest.fixture
def store(tmp_path):
    return GmailStore(tmp_path / 'gmail-inbox')


def _record(uid=1, uidvalidity=100, **overrides):
    return {'email_id': f'gmail_{uidvalidity}_{uid}', 'from': 'a@example.com', 'to': 'b@example.com',
            'subject': 'Docs', 'body': 'See attached', 'received_at': '2026-09-21T10:00:00+00:00',
            'source': 'gmail', 'message_id': '<abc@mail.gmail.com>',
            'gmail_uid': uid, 'gmail_uidvalidity': uidvalidity, **overrides}


def test_ingest_with_no_attachments(store):
    record = _record()
    full = store.ingest(record, [])
    assert full['attachments'] == []
    assert 'skipped_attachments' not in full
    assert store.emails() == [full]


def test_ingest_persists_valid_attachments(store):
    record = _record()
    full = store.ingest(record, [('SI_123.pdf', b'%PDF-fake')])
    assert full['attachments'] == [f"gmail/{record['email_id']}/SI_123.pdf"]
    assert store.read_bytes(full['attachments'][0]) == b'%PDF-fake'


def test_ingest_skips_invalid_attachment_but_keeps_message(store):
    record = _record()
    # .exe is not in ALLOWED_EXTENSIONS -- must be skipped, not rejected.
    full = store.ingest(record, [('malware.exe', b'MZ...')])
    assert full['attachments'] == []
    assert full['skipped_attachments'][0]['name'] == 'malware.exe'
    assert store.exists(record['email_id'])


def test_ingest_skips_attachment_with_wrong_magic_bytes(store):
    record = _record()
    full = store.ingest(record, [('fake.pdf', b'not really a pdf')])
    assert full['attachments'] == []
    assert 'fake.pdf' in full['skipped_attachments'][0]['name']


def test_ingest_mixes_kept_and_skipped_attachments(store):
    record = _record()
    full = store.ingest(record, [('SI_123.pdf', b'%PDF-ok'), ('bad.exe', b'MZ')])
    assert full['attachments'] == [f"gmail/{record['email_id']}/SI_123.pdf"]
    assert len(full['skipped_attachments']) == 1


def test_ingest_is_idempotent_on_email_id(store):
    record = _record()
    first = store.ingest(record, [('SI_123.pdf', b'%PDF-first')])
    # Simulate a poller retry after a crash: same uid/uidvalidity, re-ingested.
    second = store.ingest(record, [('SI_123.pdf', b'%PDF-second-should-be-ignored')])
    assert first == second
    assert store.read_bytes(first['attachments'][0]) == b'%PDF-first'


def test_emails_lists_newest_first(store):
    older = store.ingest(_record(uid=1), [])
    newer = store.ingest(_record(uid=2, **{'received_at': '2026-09-22T10:00:00+00:00'}), [])
    assert [e['email_id'] for e in store.emails()] == [newer['email_id'], older['email_id']]


def test_emails_skips_malformed_records(store):
    store.ingest(_record(), [])
    bogus = store.root / 'gmail_999_999'
    bogus.mkdir(parents=True)
    (bogus / 'email.json').write_text('not json')
    assert len(store.emails()) == 1


def test_resolve_rejects_path_traversal(store):
    record = _record()
    store.ingest(record, [('SI_123.pdf', b'%PDF-ok')])
    with pytest.raises(ValueError):
        store.resolve(record['email_id'], f"gmail/{record['email_id']}/../../etc/passwd")


def test_resolve_rejects_mismatched_email_id(store):
    a = store.ingest(_record(uid=1), [('SI.pdf', b'%PDF-a')])
    store.ingest(_record(uid=2), [])
    with pytest.raises(ValueError):
        store.resolve('gmail_100_2', a['attachments'][0])


def test_read_bytes_infers_email_id_from_path(store):
    record = _record()
    full = store.ingest(record, [('SI_123.pdf', b'%PDF-ok')])
    assert store.read_bytes(full['attachments'][0]) == b'%PDF-ok'
