from threading import Event

import pytest

from averis_email import gmail_poller
from averis_email.gmail_client import GmailAuthError
from averis_email.gmail_poller import GmailPoller, PollOutcome, run_once
from averis_email.gmail_store import GmailStore
from averis_email.settings_store import GmailSettingsStore


def _raw(subject='New shipment'):
    return (f'From: shipper@example.com\r\nTo: ops@example.com\r\n'
            f'Subject: {subject}\r\nDate: Tue, 22 Sep 2026 10:00:00 +0000\r\n'
            '\r\nPlease review the attached shipping documents.').encode()


@pytest.fixture
def configured(tmp_path):
    settings = GmailSettingsStore(tmp_path / 'gmail.json')
    settings.save('ops@example.com', password='app-password', enabled=True)
    return settings, GmailStore(tmp_path / 'gmail-inbox')


def test_first_cycle_baselines_without_backfilling(configured, monkeypatch):
    settings, store = configured
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (1001, 51))
    fetch = lambda *_: pytest.fail('baseline must not fetch existing messages')
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since', fetch)

    outcome = run_once(settings, store)

    assert outcome == PollOutcome('baselined', last_uid=50)
    assert settings.get()['uidvalidity'] == 1001
    assert settings.get()['last_uid'] == 50
    assert store.emails() == []


def test_normal_cycle_ingests_and_checkpoints_each_uid(configured, monkeypatch):
    settings, store = configured
    settings.set_sync_state(uidvalidity=1001, last_uid=50)
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (1001, 53))
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since',
                        lambda *args: (1001, [(51, _raw('One'), None), (52, _raw('Two'), None)]))

    outcome = run_once(settings, store)

    assert outcome == PollOutcome('ok', ingested=2, skipped=0, last_uid=52)
    assert settings.get()['last_uid'] == 52
    assert settings.get()['ingested_count'] == 2
    assert len(store.emails()) == 2


def test_uidvalidity_change_rebaselines_without_fetch(configured, monkeypatch):
    settings, store = configured
    settings.set_sync_state(uidvalidity=1001, last_uid=50)
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (2002, 8))
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since',
                        lambda *_: pytest.fail('changed mailbox must be rebaselined'))

    outcome = run_once(settings, store)

    assert outcome.status == 'baselined'
    assert settings.get()['uidvalidity'] == 2002
    assert settings.get()['last_uid'] == 7


def test_skipped_and_malformed_messages_do_not_wedge_checkpoint(configured, monkeypatch):
    settings, store = configured
    settings.set_sync_state(uidvalidity=1001, last_uid=50)
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (1001, 53))
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since', lambda *_: (
        1001, [(51, None, 'too large'), (52, b'bad', None)]))
    monkeypatch.setattr(gmail_poller.gmail_mime, 'parse_message',
                        lambda *_: (_ for _ in ()).throw(ValueError('malformed MIME')))

    outcome = run_once(settings, store)

    assert outcome.skipped == 2
    assert settings.get()['last_uid'] == 52
    assert 'malformed MIME' in settings.get()['last_error']


def test_storage_failure_does_not_advance_checkpoint(configured, monkeypatch):
    settings, store = configured
    settings.set_sync_state(uidvalidity=1001, last_uid=50)
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (1001, 52))
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since',
                        lambda *_: (1001, [(51, _raw(), None)]))
    monkeypatch.setattr(store, 'ingest', lambda *_: (_ for _ in ()).throw(OSError('disk full')))

    with pytest.raises(OSError, match='disk full'):
        run_once(settings, store)
    assert settings.get()['last_uid'] == 50


def test_retry_after_checkpoint_loss_is_idempotent(configured, monkeypatch):
    settings, store = configured
    settings.set_sync_state(uidvalidity=1001, last_uid=50)
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status', lambda *_: (1001, 52))
    monkeypatch.setattr(gmail_poller.gmail_client, 'fetch_since',
                        lambda *_: (1001, [(51, _raw(), None)]))
    assert run_once(settings, store).ingested == 1

    settings.set_sync_state(last_uid=50)
    assert run_once(settings, store).ingested == 0
    assert settings.get()['ingested_count'] == 1
    assert len(store.emails()) == 1


def test_auth_failure_is_exposed_in_settings(configured, monkeypatch):
    settings, store = configured
    monkeypatch.setattr(gmail_poller.gmail_client, 'mailbox_status',
                        lambda *_: (_ for _ in ()).throw(GmailAuthError('bad password')))
    with pytest.raises(GmailAuthError):
        run_once(settings, store)
    assert settings.get()['last_error'] == 'bad password'
    assert settings.get()['last_poll_at'] is not None


def test_thread_starts_runs_and_stops(configured, monkeypatch):
    settings, store = configured
    called = Event()

    def fake_run_once(*_args):
        called.set()
        return PollOutcome('ok')

    monkeypatch.setattr(gmail_poller, 'run_once', fake_run_once)
    poller = GmailPoller(settings, store, interval=60)
    assert poller.start() is True
    assert poller.start() is False
    assert called.wait(1)
    assert poller.stop(timeout=1) is True
    assert poller.running is False

