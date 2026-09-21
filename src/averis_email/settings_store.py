"""Persisted Gmail ingestion settings: mailbox address, app password, enabled
flag and poll checkpoint. A JSON file rather than an environment variable,
because this is meant to be changed from the Settings page -- no SSH, no
restart -- and the poller reads it fresh on every cycle.
"""
import json
import os
import re
from pathlib import Path

ADDRESS_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
DEFAULTS = {
    'address': None, 'password': None, 'enabled': False,
    'uidvalidity': None, 'last_uid': None,
    'last_poll_at': None, 'last_error': None, 'ingested_count': 0,
}


class GmailSettingsError(ValueError):
    """A user-facing 422 validation failure."""


class GmailSettingsStore:
    def __init__(self, path):
        self.path = Path(path)

    def _read(self):
        if not self.path.is_file():
            return dict(DEFAULTS)
        try:
            data = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return dict(DEFAULTS)
        return {**DEFAULTS, **data}

    def _write(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        os.chmod(self.path.parent, 0o700)
        staging = self.path.with_name(f'.tmp-{self.path.name}')
        staging.write_text(json.dumps(data))
        os.chmod(staging, 0o600)
        os.replace(staging, self.path)

    def get(self):
        """Full record, including the password. Internal use only (the
        poller and the test-connection endpoint) -- never return this
        directly from an API response."""
        return self._read()

    def public(self):
        """API-safe view: the password itself is never exposed."""
        data = self._read()
        return {
            'address': data['address'],
            'configured': bool(data['address'] and data['password']),
            'enabled': data['enabled'],
            'last_poll_at': data['last_poll_at'],
            'last_error': data['last_error'],
            'ingested_count': data['ingested_count'],
        }

    def save(self, address, password=None, enabled=None):
        """Update address/password/enabled. `password=None` keeps whatever
        is already stored; there is no way to set a blank password. To
        remove credentials entirely, call clear()."""
        address = (address or '').strip()
        if not ADDRESS_RE.match(address):
            raise GmailSettingsError('Enter a valid email address')
        data = self._read()
        if password is not None:
            if not password.strip():
                raise GmailSettingsError('App password cannot be blank')
            data['password'] = password
        elif not data.get('password'):
            raise GmailSettingsError('An app password is required')
        if data.get('address') != address:
            # Switching mailboxes invalidates the old UID checkpoint --
            # ingestion for the new address starts from its current tip.
            data['uidvalidity'] = None
            data['last_uid'] = None
            data['ingested_count'] = 0
        data['address'] = address
        if enabled is not None:
            data['enabled'] = enabled
        data['last_error'] = None
        self._write(data)
        return data

    def clear(self):
        self._write(dict(DEFAULTS))

    def set_sync_state(self, **fields):
        """Poller-only: persist uidvalidity/last_uid/last_poll_at/last_error/
        ingested_count without touching address/password/enabled."""
        data = self._read()
        data.update(fields)
        self._write(data)
