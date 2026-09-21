import json
import stat

import pytest

from averis_email.settings_store import GmailSettingsError, GmailSettingsStore


@pytest.fixture
def store(tmp_path):
    return GmailSettingsStore(tmp_path / 'gmail-config.json')


def test_defaults_when_unconfigured(store):
    assert store.public() == {'address': None, 'configured': False, 'enabled': False,
                              'last_poll_at': None, 'last_error': None, 'ingested_count': 0}


def test_save_requires_valid_address(store):
    with pytest.raises(GmailSettingsError):
        store.save('not-an-email', password='app-password-123')


def test_save_requires_password_on_first_save(store):
    with pytest.raises(GmailSettingsError):
        store.save('ops@example.com')


def test_save_then_public_never_exposes_password(store):
    store.save('ops@example.com', password='app-password-123', enabled=True)
    public = store.public()
    assert public['address'] == 'ops@example.com'
    assert public['configured'] is True
    assert public['enabled'] is True
    assert 'password' not in public
    raw = json.loads(store.path.read_text())
    assert raw['password'] == 'app-password-123'


def test_resave_without_password_keeps_existing(store):
    store.save('ops@example.com', password='app-password-123')
    store.save('ops@example.com', enabled=True)
    assert store.get()['password'] == 'app-password-123'
    assert store.public()['enabled'] is True


def test_blank_password_is_rejected_not_treated_as_clear(store):
    store.save('ops@example.com', password='app-password-123')
    with pytest.raises(GmailSettingsError):
        store.save('ops@example.com', password='   ')
    assert store.get()['password'] == 'app-password-123'


def test_changing_address_resets_uid_checkpoint(store):
    store.save('old@example.com', password='pw')
    store.set_sync_state(uidvalidity=42, last_uid=99, ingested_count=7)
    store.save('new@example.com', password='pw2')
    data = store.get()
    assert data['uidvalidity'] is None
    assert data['last_uid'] is None
    assert data['ingested_count'] == 0


def test_clear_removes_everything(store):
    store.save('ops@example.com', password='app-password-123', enabled=True)
    store.clear()
    assert store.public()['configured'] is False
    assert store.get()['password'] is None


def test_set_sync_state_preserves_credentials(store):
    store.save('ops@example.com', password='app-password-123', enabled=True)
    store.set_sync_state(last_poll_at='2026-09-22T00:00:00Z', last_error=None, ingested_count=3)
    data = store.get()
    assert data['address'] == 'ops@example.com'
    assert data['password'] == 'app-password-123'
    assert data['ingested_count'] == 3


def test_file_written_with_restrictive_permissions(store):
    store.save('ops@example.com', password='app-password-123')
    mode = stat.S_IMODE(store.path.stat().st_mode)
    assert mode == 0o600
    dir_mode = stat.S_IMODE(store.path.parent.stat().st_mode)
    assert dir_mode == 0o700


def test_corrupt_file_falls_back_to_defaults(store):
    store.path.parent.mkdir(parents=True, exist_ok=True)
    store.path.write_text('not json')
    assert store.public()['configured'] is False
