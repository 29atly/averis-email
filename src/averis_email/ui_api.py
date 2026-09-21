"""Frontend contracts and durable local workflow state (one API worker)."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from averis_email.schemas import FIELDS, FieldValue, PipelineResult
from averis_email.stages.normalizer import NORMALIZERS
from averis_email.stages.validation import _is_missing_value


class Evidence(BaseModel):
    file_path: str | None = None
    page_number: int | None = None
    source_text: str | None = None
    raw: str | None = None
    normalized: str | int | float | None = None
    corrected: bool = False


class Attachment(BaseModel):
    name: str
    path: str
    download_url: str


class Activity(BaseModel):
    timestamp: str
    title: str
    detail: str
    warning: bool = False


class Case(BaseModel):
    id: str
    subject: str
    sender: str
    recipient: str
    body: str
    time: str
    receivedLabel: str
    category: str = "unclassified"
    status: Literal['pending', 'review', 'complete'] = 'pending'
    attachments: list[Attachment] = Field(default_factory=list)
    siFile: str | None = None
    blFile: str | None = None
    processingTime: str | None = None
    values: dict[str, list[Evidence]] = Field(default_factory=dict)
    reviewFields: list[str] = Field(default_factory=list)
    reviewReasonCode: str | None = None
    reviewReason: str | None = None
    error: str | None = None
    defectFields: list[str] = Field(default_factory=list)
    activity: list[Activity] = Field(default_factory=list)
    evidenceCoverage: int = 0
    revision: int = 0
    canConfirmValues: bool = False
    reviewStage: str | None = None


class ReviewRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    si: dict[str, str] = Field(default_factory=dict)
    bl: dict[str, str] = Field(default_factory=dict)
    category: Literal['BL_COMPARISON', 'SI_REQUEST', 'INVOICE_QUERY', 'GENERAL', 'SPAM'] | None = None

    @field_validator('si', 'bl')
    @classmethod
    def validate_fields(cls, values):
        for key, value in values.items():
            if key not in FIELDS or _is_missing_value(key, value):
                raise ValueError(f'Invalid or missing shipping value: {key}')
        return values


class StateStore:
    def __init__(self, path, namespace=''):
        self.path = Path(path)
        self.namespace = namespace

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(self.path)
        try:
            with db:
                db.execute('CREATE TABLE IF NOT EXISTS cases (id TEXT PRIMARY KEY, fingerprint TEXT, payload TEXT)')
                yield db
        finally:
            db.close()

    def fingerprint(self, email):
        return hashlib.sha256(json.dumps([self.namespace, email], sort_keys=True).encode()).hexdigest()

    def next_revision(self, email):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM cases WHERE id=?', (email['email_id'],)).fetchone()
        return json.loads(row[0])['revision'] + 1 if row else 1

    def get_many(self, emails):
        with self.connect() as db:
            rows = {row[0]: row[1:] for row in db.execute('SELECT id, fingerprint, payload FROM cases')}
        return {email['email_id']: json.loads(rows[email['email_id']][1]) for email in emails
                if email['email_id'] in rows and rows[email['email_id']][0] == self.fingerprint(email)}

    def get(self, email):
        with self.connect() as db:
            row = db.execute('SELECT payload FROM cases WHERE id=? AND fingerprint=?',
                             (email['email_id'], self.fingerprint(email))).fetchone()
        return json.loads(row[0]) if row else None

    def put(self, email, state):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cases VALUES (?, ?, ?)',
                       (email['email_id'], self.fingerprint(email), json.dumps(state)))


def _parse_stamp(stamp):
    if not stamp:
        return None
    try:
        parsed = datetime.fromisoformat(str(stamp).replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _short_time(stamp):
    """Compact received-at label for the narrow work-queue column."""
    parsed = _parse_stamp(stamp)
    if parsed is None:
        return str(stamp)
    days = (datetime.now().date() - parsed.date()).days
    if days == 0:
        return parsed.strftime('%H:%M')
    if days == 1:
        return 'Yesterday'
    if 0 < days < 7:
        return parsed.strftime('%A')
    return f'{parsed.day} {parsed.strftime("%b")}'


def _received_label(stamp):
    """Fuller received-at label for detail views, e.g. 'Yesterday at 16:27'."""
    parsed = _parse_stamp(stamp)
    if parsed is None:
        return str(stamp)
    days = (datetime.now().date() - parsed.date()).days
    if days == 0:
        return parsed.strftime('%H:%M')
    return f'{_short_time(stamp)} at {parsed.strftime("%H:%M")}'


def event(title, detail, warning=False):
    return dict(timestamp=datetime.now(timezone.utc).isoformat(), title=title,
                detail=detail, warning=warning)


def evidence(doc, key, corrected):
    if doc is None:
        return Evidence()
    field = doc.fields.get(key)
    if isinstance(field, FieldValue):
        field = field.model_dump()
    if not isinstance(field, dict):
        field = {'value': field}
    raw = field.get('value')
    return Evidence(file_path=field.get('source_file') or doc.attachment_path,
                    page_number=field.get('source_page'), source_text=field.get('raw_text'),
                    raw=None if raw is None else str(raw),
                    normalized=None if _is_missing_value(key, raw) else NORMALIZERS[key](raw),
                    corrected=corrected)


def to_case(email, state=None):
    from urllib.parse import quote
    stamp = email.get('received_at') or email.get('date') or email.get('timestamp') or ''
    recipient = email.get('to') or ''
    if isinstance(recipient, list):
        recipient = ', '.join(recipient)
    case = Case(id=email['email_id'], subject=email.get('subject') or '',
                sender=email.get('from') or '', recipient=recipient,
                body=email.get('body') or '', time=_short_time(stamp), receivedLabel=_received_label(stamp),
                attachments=[Attachment(name=Path(path).name, path=path,
                    download_url=f"/emails/{quote(email['email_id'], safe='')}/attachments/{i}")
                    for i, path in enumerate(email.get('attachments') or []) if isinstance(path, str)])
    if not state:
        return case
    result = PipelineResult.model_validate(state['result'])
    case.category = result.category.lower()
    case.status = 'review' if result.status == 'NEEDS_REVIEW' else 'complete'
    case.processingTime = f"{state['duration']:.2f}s"
    case.revision = state['revision']
    case.activity = [Activity(**item) for item in state['activity']]
    case.reviewStage = result.review_context.stage if result.review_context else None
    case.reviewReasonCode = result.review_reason
    case.error = result.error
    case.defectFields = result.defect_fields
    case.reviewReason = result.error or {
        'missing_value': 'Required shipping values are missing. Confirm each affected document separately.',
        'missing_attachment': 'The required SI or draft BL attachment is missing. Update the source email and retry.',
        'wrong_doc_type': 'The attachments could not be identified as SI and draft BL. Check the source files and retry.',
        'unreadable': 'Processing could not produce a dependable result. Check the original email and attachments, then retry.',
    }.get(result.review_reason)
    if 'classification' in result.diff_detail:
        case.reviewReason = result.diff_detail['classification'].get('reason') or case.reviewReason
    case.siFile = result.si.attachment_path if result.si else None
    case.blFile = result.bl.attachment_path if result.bl else None
    if result.category == 'BL_COMPARISON':
        corrections = state.get('corrections', {})
        case.values = {key: [evidence(result.si, key, key in corrections.get('si', {})),
                             evidence(result.bl, key, key in corrections.get('bl', {}))] for key in FIELDS}
        case.reviewFields = [key for key, pair in case.values.items() if any(v.normalized is None for v in pair)]
        case.evidenceCoverage = sum(all(v.source_text and v.page_number is not None and v.file_path for v in pair)
                                    for pair in case.values.values())
        case.canConfirmValues = bool(case.status == 'review' and result.review_reason == 'missing_value'
                                     and result.si and result.bl and result.si.readable and result.bl.readable)
    return case
