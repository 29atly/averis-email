"""Locally stored, manually composed emails.

Kept entirely separate from AVERIS_INBOX_SOURCE, which is the organizers'
dataset and may be a read-only HTTP URL. Manual records are shaped exactly
like an inbox record (email_id/from/to/subject/body/attachments) so the rest
of the pipeline and UI need no special casing.
"""
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from urllib.parse import unquote
from uuid import uuid4

PREFIX = 'manual'
ID_RE = re.compile(r'^manual_[0-9a-f]{12}$')
FILENAME_RE = re.compile(r'^[A-Za-z0-9 ._()\[\]-]{1,120}$')
ALLOWED_EXTENSIONS = {'.pdf', '.xlsx', '.txt', '.docx', '.docs'}
MAGIC = {
    '.pdf': (b'%PDF-',),
    '.docx': (b'PK\x03\x04',),
    '.docs': (b'PK\x03\x04',),
    '.xlsx': (b'PK\x03\x04',),
}
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024
MAX_FILES = 10
MAX_SUBJECT_CHARS = 300
MAX_CONTENT_CHARS = 100_000


class ManualUploadError(ValueError):
    """A user-facing 422 (or 413 for size) validation failure."""
    def __init__(self, message, status_code=422):
        super().__init__(message)
        self.status_code = status_code


def list_records(root, id_re):
    """Newest-first records from '<root>/<id>/email.json' directories whose
    name matches id_re. Unreadable or malformed records are skipped, not
    raised. Shared by ManualStore and GmailStore -- same on-disk shape,
    different id prefix."""
    root = Path(root)
    if not root.is_dir():
        return []
    records = []
    for directory in root.iterdir():
        if not id_re.match(directory.name) or not directory.is_dir():
            continue
        try:
            record = json.loads((directory / 'email.json').read_text())
        except (OSError, ValueError):
            continue
        if record.get('email_id') != directory.name:
            continue
        records.append(record)
    records.sort(key=lambda r: r.get('received_at') or '', reverse=True)
    return records


def resolve_prefixed_path(root, prefix, email_id, path):
    """Validate and resolve a '<prefix>/<email_id>/<name>' attachment path to
    a file under '<root>/<email_id>/files/'. Raises ValueError. Shared so a
    path-traversal fix only has to happen in one place."""
    if unquote(path) != path or '\\' in path or '?' in path or '#' in path:
        raise ValueError('invalid attachment path')
    parts = PurePosixPath(path).parts
    if len(parts) != 3 or parts[0] != prefix or '..' in parts:
        raise ValueError('invalid attachment path')
    if parts[1] != email_id:
        raise ValueError('attachment does not belong to this case')
    root = Path(root)
    files_dir = (root / email_id / 'files').resolve()
    target = (root / parts[1] / 'files' / parts[2]).resolve()
    if not target.is_relative_to(files_dir) or not target.is_file() or target.is_symlink():
        raise ValueError('attachment not found')
    return target


def validate_filename(filename):
    name = PurePosixPath((filename or '').replace('\\', '/')).name
    if not name or name in ('.', '..'):
        raise ManualUploadError('Attachment is missing a filename')
    if unquote(name) != name:
        raise ManualUploadError(f'Attachment filename is not allowed: {filename}')
    if name.startswith('.'):
        raise ManualUploadError(f'Attachment filename is not allowed: {filename}')
    if not FILENAME_RE.match(name):
        raise ManualUploadError(f'Attachment filename is not allowed: {filename}')
    suffix = Path(name).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        raise ManualUploadError(f'Unsupported attachment type: {name}. Allowed: .pdf, .xlsx, .txt, .docx, .docs')
    return name, suffix


def validate_content(name, suffix, data):
    if not data:
        raise ManualUploadError(f'Attachment is empty: {name}')
    if len(data) > MAX_FILE_BYTES:
        raise ManualUploadError(f'Attachment exceeds the {MAX_FILE_BYTES // (1024*1024)} MB limit: {name}', 413)
    magic = MAGIC.get(suffix)
    if magic and not any(data.startswith(m) for m in magic):
        raise ManualUploadError(f'Attachment content does not match its extension: {name}')
    if suffix == '.txt' and b'\x00' in data:
        raise ManualUploadError(f'Attachment is not valid text: {name}')


class ManualStore:
    def __init__(self, root):
        self.root = Path(root)

    # -- listing -----------------------------------------------------
    def emails(self):
        """Newest first. Unreadable or malformed records are skipped, not raised."""
        return list_records(self.root, ID_RE)

    # -- creation ------------------------------------------------------
    def create(self, subject, body, files):
        """files: list of (original_filename, bytes). Returns the new record."""
        subject = (subject or '').strip()[:MAX_SUBJECT_CHARS]
        body = (body or '').strip()[:MAX_CONTENT_CHARS]
        if not subject and not body and not files:
            raise ManualUploadError('Provide a subject, content, or at least one attachment')
        if len(files) > MAX_FILES:
            raise ManualUploadError(f'Too many attachments (max {MAX_FILES})')

        cleaned = []
        seen_lower = set()
        total = 0
        for filename, data in files:
            name, suffix = validate_filename(filename)
            if name.lower() in seen_lower:
                raise ManualUploadError(f'Duplicate attachment name: {name}')
            seen_lower.add(name.lower())
            validate_content(name, suffix, data)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ManualUploadError(f'Attachments exceed the {MAX_TOTAL_BYTES // (1024*1024)} MB total limit', 413)
            cleaned.append((name, data))

        self.root.mkdir(parents=True, exist_ok=True)
        for _ in range(3):
            email_id = f'manual_{uuid4().hex[:12]}'
            staging = self.root / f'.tmp-{email_id}'
            try:
                staging.mkdir()
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError('Could not allocate a manual email id')

        files_dir = staging / 'files'
        files_dir.mkdir()
        attachments = []
        for name, data in cleaned:
            path = files_dir / name
            path.write_bytes(data)
            os.chmod(path, 0o600)
            attachments.append(f'{PREFIX}/{email_id}/{name}')

        record = {
            'email_id': email_id, 'from': 'you@yourcompany.com', 'to': ['Operations Team'],
            'subject': subject, 'body': body, 'attachments': attachments,
            'received_at': datetime.now(timezone.utc).isoformat(), 'source': 'manual',
        }
        (staging / 'email.json').write_text(json.dumps(record))
        os.chmod(staging / 'email.json', 0o600)

        final = self.root / email_id
        os.replace(staging, final)
        return record

    # -- attachment reads ------------------------------------------------
    def resolve(self, email_id, path):
        """Validate and resolve a 'manual/<email_id>/<name>' path. Raises ValueError."""
        return resolve_prefixed_path(self.root, PREFIX, email_id, path)

    def read_bytes(self, path, email_id=None):
        parts = PurePosixPath(path).parts
        target = self.resolve(email_id or (parts[1] if len(parts) > 1 else ''), path)
        return target.read_bytes()


class CompositeLoader:
    """A loader for run_pipeline() that routes manual/... and gmail/... paths
    to their local stores and everything else to the configured inbox
    source. `gmail` is optional so existing callers/tests are unaffected."""
    def __init__(self, inbox, manual, gmail=None):
        self.inbox = inbox
        self.manual = manual
        self.gmail = gmail
        self.source = inbox.source
        self.is_http = inbox.is_http

    def read_bytes(self, path):
        if self.gmail is not None and path.startswith('gmail/'):
            return self.gmail.read_bytes(path)
        if path.startswith(f'{PREFIX}/'):
            return self.manual.read_bytes(path)
        return self.inbox.read_bytes(path)
