"""Local API and frontend. Run uvicorn averis_email.web:app --port 8000.

Use one worker: pipeline executions and review updates are serialized locally.
"""
import mimetypes
import os
from pathlib import Path, PurePosixPath
from threading import RLock
from time import perf_counter
from urllib.parse import quote, unquote
from urllib.error import URLError

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from averis_email.data_loader import Inbox
from averis_email.manual_store import CompositeLoader, ManualStore, ManualUploadError
from averis_email.orchestrator import run_pipeline
from averis_email.schemas import FieldValue, PipelineResult
from averis_email.stages import comparison, validation
from averis_email.ui_api import Case, ReviewRequest, StateStore, event, to_case

load_dotenv()
app = FastAPI(title='Averis Email Pipeline API')
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_methods=['*'], allow_headers=['*'])
INBOX = Inbox(os.getenv('AVERIS_INBOX_SOURCE', 'data'))
MANUAL = ManualStore(os.getenv('AVERIS_MANUAL_UPLOADS', '.cache/manual-uploads'))
STORE = StateStore(os.getenv('AVERIS_UI_STATE', '.cache/ui-state.sqlite3'), namespace=INBOX.source)
LOCK = RLock()


class EmailSummary(BaseModel):
    email_id: str
    sender: str | None = None
    subject: str | None = None
    has_attachments: bool


def emails():
    manual = MANUAL.emails()
    try:
        records = INBOX.emails()
        if not records and not manual and not INBOX.is_http and not (Path(INBOX.source) / 'inbox').is_dir():
            raise HTTPException(503, 'Inbox not configured: set AVERIS_INBOX_SOURCE to the folder containing inbox/ and attachments/.')
        return manual + records
    except (OSError, ValueError, URLError) as exc:
        if manual:
            return manual
        raise HTTPException(503, 'Inbox source is unavailable') from exc


def find_email(email_id):
    email = next((e for e in emails() if e['email_id'] == email_id), None)
    if email is None:
        raise HTTPException(404, 'email not found')
    return email


def process(email, previous=None, category_override=None, attachment_override=None):
    started = perf_counter()
    loader = CompositeLoader(INBOX, MANUAL)
    kwargs = {}
    if category_override:
        kwargs['category_override'] = category_override
    if attachment_override:
        kwargs['attachment_override'] = attachment_override
    try:
        result = run_pipeline(loader, email, **kwargs)
    except Exception:
        result = PipelineResult(email_id=email['email_id'], category='GENERAL', status='NEEDS_REVIEW',
                                review_reason='unreadable', error='Pipeline failed. Check server configuration and retry.')
    state = dict(result=result.model_dump(mode='json'), duration=perf_counter() - started,
                 revision=STORE.next_revision(email),
                 activity=(previous or {}).get('activity', []) + [event(
                     'Processing retried' if previous else 'Email processed',
                     f"{result.category}: {result.status or 'Classification complete'}",
                     result.status == 'NEEDS_REVIEW')])
    STORE.put(email, state)
    return state


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/emails', response_model=list[EmailSummary])
def list_emails():
    return [EmailSummary(email_id=e['email_id'], sender=e.get('from'), subject=e.get('subject'),
                         has_attachments=bool(e.get('attachments'))) for e in emails()]


@app.get('/emails/{email_id}', response_model=PipelineResult)
def get_email_result(email_id: str):
    with LOCK:
        email = find_email(email_id)
        state = STORE.get(email) or process(email)
        return PipelineResult.model_validate(state['result'])


def _validate_inbox_path(path):
    parsed = PurePosixPath(path)
    if (parsed.is_absolute() or '..' in parsed.parts or '\\' in path or
            unquote(path) != path or '?' in path or '#' in path or
            not parsed.parts or parsed.parts[0] != 'attachments'):
        raise HTTPException(400, 'invalid attachment path')
    if not INBOX.is_http:
        root = (Path(INBOX.source) / 'attachments').resolve()
        if not (Path(INBOX.source) / path).resolve().is_relative_to(root):
            raise HTTPException(400, 'invalid attachment path')


@app.get('/emails/{email_id}/attachments/{attachment_index}')
def get_original_attachment(email_id: str, attachment_index: int):
    # Resolve only attachments belonging to this email; never accept a client path.
    email = find_email(email_id)
    attachments = email.get('attachments') or []
    if attachment_index < 0 or attachment_index >= len(attachments):
        raise HTTPException(404, 'attachment not found')
    path = attachments[attachment_index]
    if not isinstance(path, str):
        raise HTTPException(400, 'invalid attachment path')
    is_manual = path.startswith('manual/')
    if not is_manual:
        _validate_inbox_path(path)
    try:
        if is_manual:
            content = MANUAL.read_bytes(path, email_id=email_id)
        else:
            content = INBOX.read_bytes(path)
    except (OSError, URLError) as exc:
        raise HTTPException(404, 'attachment unavailable') from exc
    except ValueError as exc:
        raise HTTPException(400, 'invalid attachment path') from exc
    return Response(content, media_type=mimetypes.guess_type(path)[0] or 'application/octet-stream',
                    headers={'Content-Disposition': f"attachment; filename*=UTF-8''{quote(PurePosixPath(path).name, safe='')}",
                             'X-Content-Type-Options': 'nosniff'})


@app.get('/cases', response_model=list[Case])
def list_cases(q: str = '', category: str | None = None, status: str | None = None,
               limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
    """List without inference. Unprocessed emails have pending/unclassified state."""
    with LOCK:
        records = emails()
        states = STORE.get_many(records)
        cases = [to_case(email, states.get(email['email_id'])) for email in records]
    return [case for case in cases if
            (not q or q.casefold() in f'{case.id} {case.subject} {case.sender} {case.body}'.casefold()) and
            (category is None or case.category == category.lower()) and
            (status is None or case.status == status)][offset:offset + limit]


@app.get('/cases/{email_id}', response_model=Case)
@app.post('/cases/{email_id}/process', response_model=Case)
def get_case(email_id: str):
    """GET processes on first access; POST .../process is the same idempotent
    step under a name the bulk-processing UI can call explicitly. Neither
    discards saved human corrections the way retry does."""
    with LOCK:
        email = find_email(email_id)
        return to_case(email, STORE.get(email) or process(email))


@app.post('/cases', response_model=Case, status_code=201)
def create_case(subject: str = Form(''), content: str = Form(''), files: list[UploadFile] = File(default=[])):
    """Persist a manually composed email. Does not run the pipeline: a slow
    classification call inside this request would risk losing the upload to
    a client/proxy timeout. Call POST /cases/{id}/process afterward."""
    with LOCK:
        try:
            uploaded = [(f.filename, f.file.read()) for f in files]
            record = MANUAL.create(subject, content, uploaded)
        except ManualUploadError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc
        return to_case(record, None)


@app.post('/cases/{email_id}/retry', response_model=Case)
def retry_case(email_id: str):
    """Run synchronously against the current source; discard previous corrections."""
    with LOCK:
        email = find_email(email_id)
        return to_case(email, process(email, STORE.get(email)))


@app.post('/cases/{email_id}/review', response_model=Case)
def review_case(email_id: str, request: ReviewRequest):
    with LOCK:
        email = find_email(email_id)
        state = STORE.get(email)
        if not state or request.revision != state['revision']:
            raise HTTPException(409, 'Case changed. Reload before confirming values.')
        result = PipelineResult.model_validate(state['result'])
        if result.status != 'NEEDS_REVIEW':
            raise HTTPException(409, 'Case is not awaiting review')
        if request.si_attachment or request.bl_attachment:
            if request.category or request.si or request.bl:
                raise HTTPException(422, 'Attachment classification cannot include a category change or shipping field corrections')
            if not request.si_attachment or not request.bl_attachment:
                raise HTTPException(422, 'Choose both the shipping instruction and bill of lading attachment')
            if request.si_attachment == request.bl_attachment:
                raise HTTPException(422, 'The shipping instruction and bill of lading must be different attachments')
            if result.category != 'BL_COMPARISON' or result.review_reason not in ('missing_attachment', 'wrong_doc_type'):
                raise HTTPException(422, 'This case does not need manual attachment classification')
            valid_paths = {path for path in (email.get('attachments') or []) if isinstance(path, str)}
            if request.si_attachment not in valid_paths or request.bl_attachment not in valid_paths:
                raise HTTPException(422, 'Unknown attachment selected')
            state = process(email, state, attachment_override=(request.si_attachment, request.bl_attachment))
            result = PipelineResult.model_validate(state['result'])
        elif request.category:
            if result.si or result.bl or request.si or request.bl:
                raise HTTPException(422, 'Category confirmation cannot include shipping field corrections')
            if request.category == 'BL_COMPARISON':
                state = process(email, state, category_override=request.category)
                result = PipelineResult.model_validate(state['result'])
            else:
                result = PipelineResult(email_id=email_id, category=request.category)
        else:
            if not to_case(email, state).canConfirmValues or not (request.si or request.bl):
                raise HTTPException(422, 'This case needs source correction and retry, or category confirmation')
            for side in ('si', 'bl'):
                doc = getattr(result, side)
                for key, value in getattr(request, side).items():
                    old = doc.fields.get(key)
                    old = old.model_dump() if isinstance(old, FieldValue) else old
                    field = dict(old) if isinstance(old, dict) else {}
                    field['value'] = value.strip()
                    doc.fields[key] = FieldValue.model_validate(field)
            if validation.missing_fields(result.si, result.bl):
                raise HTTPException(422, 'Confirm all missing SI and BL values before continuing')
            defects, detail = comparison.compare_fields(result.si, result.bl)
            result.status = 'MISMATCH' if defects else 'OK'
            result.has_defect, result.defect_fields = bool(defects), defects
            result.review_reason, result.error, result.review_context = None, None, None
            result.diff_detail = {**result.diff_detail, **detail}
            result.diff_detail.pop('missing_fields', None)
        state['result'] = result.model_dump(mode='json')
        state['revision'] += 1
        state['corrections'] = {'si': request.si, 'bl': request.bl}
        state['activity'].append(event('Human review confirmed',
            f"SI: {request.si_attachment}, BL: {request.bl_attachment}" if request.si_attachment else
            f"Category: {request.category}" if request.category else
            'Corrected ' + ', '.join(f'{side}.{key}' for side in ('si', 'bl') for key in getattr(request, side))))
        STORE.put(email, state)
        return to_case(email, state)


# Keep API routes above the mount. Installed packages may omit repository assets.
FRONTEND = Path(__file__).resolve().parents[2] / 'frontend'
if FRONTEND.is_dir():
    app.mount('/ui', StaticFiles(directory=FRONTEND, html=True), name='frontend')
