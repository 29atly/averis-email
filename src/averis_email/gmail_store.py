"""Gmail-ingested mail, persisted exactly like ManualStore so read_bytes()
and emails() work with zero pipeline changes, and StateStore.fingerprint
stays stable: each record is written once from IMAP and always read back
verbatim -- never re-derived from the network on a later request.
"""
import json
import os
import re
from pathlib import Path, PurePosixPath

from averis_email.manual_store import (ManualUploadError, list_records, resolve_prefixed_path,
                                       validate_content, validate_filename)

PREFIX = 'gmail'
ID_RE = re.compile(r'^gmail_\d+_\d+$')


class GmailStore:
    def __init__(self, root):
        self.root = Path(root)

    # -- listing -----------------------------------------------------
    def emails(self):
        """Newest first. Unreadable or malformed records are skipped, not raised."""
        return list_records(self.root, ID_RE)

    def exists(self, email_id):
        return (self.root / email_id / 'email.json').is_file()

    # -- ingestion -----------------------------------------------------
    def ingest(self, record, attachments):
        """record: an email dict from gmail_mime.parse_message, without an
        'attachments' key yet. attachments: [(filename, bytes), ...].

        Idempotent on record['email_id'] -- ingesting the same UID twice
        (e.g. after a poller crash mid-cycle) returns the existing record
        unchanged rather than re-writing it, so a retry can never duplicate
        or corrupt what's on disk.

        Attachments that fail validation are skipped, not rejected: unlike
        the manual-compose form (which can hand a 422 back to the person
        typing), there's no one to correct a malformed inbound email, so the
        message is still ingested and the failure is recorded for display.
        """
        email_id = record['email_id']
        final = self.root / email_id
        if final.is_dir():
            return json.loads((final / 'email.json').read_text())

        self.root.mkdir(parents=True, exist_ok=True)
        staging = self.root / f'.tmp-{email_id}'
        files_dir = staging / 'files'
        files_dir.mkdir(parents=True)

        kept, skipped, seen_lower = [], [], set()
        for name, data in attachments:
            try:
                clean_name, suffix = validate_filename(name)
                if clean_name.lower() in seen_lower:
                    raise ManualUploadError(f'Duplicate attachment name: {clean_name}')
                validate_content(clean_name, suffix, data)
            except ManualUploadError as exc:
                skipped.append({'name': name, 'reason': str(exc)})
                continue
            seen_lower.add(clean_name.lower())
            path = files_dir / clean_name
            path.write_bytes(data)
            os.chmod(path, 0o600)
            kept.append(f'{PREFIX}/{email_id}/{clean_name}')

        full = {**record, 'attachments': kept}
        if skipped:
            full['skipped_attachments'] = skipped
        (staging / 'email.json').write_text(json.dumps(full))
        os.chmod(staging / 'email.json', 0o600)
        os.replace(staging, final)
        return full

    # -- attachment reads ------------------------------------------------
    def resolve(self, email_id, path):
        """Validate and resolve a 'gmail/<email_id>/<name>' path. Raises ValueError."""
        return resolve_prefixed_path(self.root, PREFIX, email_id, path)

    def read_bytes(self, path, email_id=None):
        parts = PurePosixPath(path).parts
        target = self.resolve(email_id or (parts[1] if len(parts) > 1 else ''), path)
        return target.read_bytes()
