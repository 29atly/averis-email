"""API contract tests; pipeline inference is stubbed, routing and storage are real."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from averis_email import web
from averis_email.gmail_client import GmailAuthError, GmailConnectionError
from averis_email.gmail_store import GmailStore
from averis_email.manual_store import ManualStore
from averis_email.schemas import FIELDS, ExtractedDoc, FieldValue, PipelineResult
from averis_email.settings_store import GmailSettingsStore
from averis_email.ui_api import StateStore


@pytest.mark.parametrize(('configured', 'expected'), [
    ('', 60),
    ('60s', 60),
    ('invalid', 60),
    ('0', 1),
    ('15', 15),
])
def test_gmail_poll_interval_is_safe(monkeypatch, configured, expected):
    monkeypatch.setenv('AVERIS_GMAIL_POLL_INTERVAL', configured)
    assert web._gmail_poll_interval() == expected


@pytest.fixture
def api(tmp_path, monkeypatch):
    # Unit/API tests must never start a real background IMAP connection.
    monkeypatch.setenv('AVERIS_GMAIL_POLL', '0')
    (tmp_path / 'inbox').mkdir()
    (tmp_path / 'attachments').mkdir()
    (tmp_path / 'attachments' / 'si.txt').write_bytes(b'original SI\x00')
    email = dict(email_id='email_1', subject='<script>test</script>', body='Compare documents',
                 attachments=['attachments/si.txt', 'attachments/bl.txt'],
                 **{'from': 'sender@example.com', 'to': ['ops@example.com']})
    inbox = web.Inbox(str(tmp_path))
    monkeypatch.setattr(inbox, 'emails', lambda: [deepcopy(email)])
    monkeypatch.setattr(web, 'INBOX', inbox)
    monkeypatch.setattr(web, 'STORE', StateStore(tmp_path / 'state.sqlite3'))
    monkeypatch.setattr(web, 'MANUAL', ManualStore(tmp_path / 'manual'))
    monkeypatch.setattr(web, 'GMAIL_SETTINGS', GmailSettingsStore(tmp_path / 'gmail-config.json'))
    monkeypatch.setattr(web, 'GMAIL_STORE', GmailStore(tmp_path / 'gmail-inbox'))
    si = ExtractedDoc(attachment_path='attachments/si.txt', fields={
        key: FieldValue(value='10' if key in ['container_count', 'gross_weight_kg'] else 'ACME',
                        source_file='attachments/si.txt', source_page=1, raw_text=f'{key}: original') for key in FIELDS})
    bl = si.model_copy(deep=True)
    bl.attachment_path = 'attachments/bl.txt'
    si.fields['container_count'].value = None
    result = PipelineResult(email_id='email_1', category='BL_COMPARISON', status='NEEDS_REVIEW',
                            review_reason='missing_value', si=si, bl=bl)
    runner = Mock(return_value=result)
    monkeypatch.setattr(web, 'run_pipeline', runner)
    with TestClient(web.app) as client:
        yield client, runner, email


def test_pending_queue_and_cached_detail(api):
    client, runner, _ = api
    listed = client.get('/cases').json()
    assert listed[0]['status'] == 'pending'
    assert listed[0]['recipient'] == 'ops@example.com'
    assert listed[0]['time'] == ''
    runner.assert_not_called()
    detail = client.get('/cases/email_1').json()
    assert detail['category'] == 'bl_comparison'
    assert detail['reviewFields'] == ['container_count']
    assert set(detail['values']) == set(FIELDS)
    assert detail['values']['container_count'][0]['normalized'] is None
    assert detail['values']['shipper'][0]['source_text'] == 'shipper: original'
    assert client.get('/emails/email_1').json()['status'] == 'NEEDS_REVIEW'
    assert client.get('/cases/email_1').json() == detail
    assert runner.call_count == 1
    assert len(client.get('/cases?q=script&status=review&category=BL_COMPARISON').json()) == 1
    assert client.get('/cases?status=complete').json() == []
    assert client.get('/cases?offset=1').json() == []
    assert client.get('/cases?limit=0').status_code == 422


def test_review_persists_compares_and_preserves_evidence(api):
    client, runner, _ = api
    case = client.get('/cases/email_1').json()
    payload = {'revision': case['revision'], 'si': {'container_count': '11'}}
    response = client.post('/cases/email_1/review', json=payload)
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed['status'] == 'complete'
    assert reviewed['defectFields'] == ['container_count']
    assert reviewed['values']['container_count'][0]['normalized'] == 11
    assert reviewed['values']['container_count'][0]['source_text'] == 'container_count: original'
    assert reviewed['values']['container_count'][0]['corrected'] is True
    assert client.get('/emails/email_1').json()['status'] == 'MISMATCH'
    # A new store instance reads the same durable result.
    web.STORE = StateStore(web.STORE.path)
    assert client.get('/cases/email_1').json() == reviewed
    assert client.post('/cases/email_1/review', json=payload).status_code == 409
    retried = client.post('/cases/email_1/retry').json()
    assert runner.call_count == 2
    assert retried['status'] == 'review'
    assert not retried['values']['container_count'][0]['corrected']
    assert len(retried['activity']) == 3


@pytest.mark.parametrize('fields', [{'unknown': 'x'}, {'container_count': 'bad'}, {'container_count': ''}, {}])
def test_invalid_review_does_not_complete(api, fields):
    client, _, _ = api
    case = client.get('/cases/email_1').json()
    response = client.post('/cases/email_1/review', json={'revision': case['revision'], 'si': fields})
    assert response.status_code == 422
    assert client.get('/cases/email_1').json()['status'] == 'review'


def test_both_sides_must_be_valid(api):
    client, runner, _ = api
    runner.return_value.bl.fields['container_count'].value = None
    case = client.get('/cases/email_1').json()
    payload = {'revision': case['revision'], 'si': {'container_count': '10'}}
    assert client.post('/cases/email_1/review', json=payload).status_code == 422
    payload['bl'] = {'container_count': '10'}
    assert client.post('/cases/email_1/review', json=payload).json()['defectFields'] == []


def test_download_and_missing_resources(api):
    client, _, _ = api
    response = client.get('/emails/email_1/attachments/0')
    assert response.content == b'original SI\x00'
    assert 'attachment;' in response.headers['content-disposition']
    for path in ['/cases/missing', '/emails/missing', '/emails/email_1/attachments/-1', '/emails/email_1/attachments/1']:
        assert client.get(path).status_code == 404
    assert client.get('/ui/').status_code == 200


@pytest.mark.parametrize('path', ['../secret', '/etc/passwd', 'attachments/../../secret', 'attachments/%2e%2e/secret'])
def test_download_blocks_unsafe_sources(api, monkeypatch, path):
    client, _, email = api
    monkeypatch.setattr(web.INBOX, 'emails', lambda: [{**email, 'attachments': [path]}])
    reader = Mock()
    monkeypatch.setattr(web.INBOX, 'read_bytes', reader)
    assert client.get('/emails/email_1/attachments/0').status_code == 400
    reader.assert_not_called()


def test_unconfigured_inbox_is_not_silently_empty(api, monkeypatch, tmp_path):
    client, _, _ = api
    monkeypatch.setattr(web, 'INBOX', web.Inbox(str(tmp_path / 'missing')))
    assert client.get('/cases').status_code == 503


def test_classification_review_is_not_reported_complete(api):
    client, runner, _ = api
    runner.return_value = PipelineResult(email_id='email_1', category='GENERAL', status='NEEDS_REVIEW',
                                         review_reason='unreadable', diff_detail={'classification': {'reason': 'Uncertain'}})
    case = client.get('/cases/email_1').json()
    assert case['status'] == 'review'
    assert case['reviewReason'] == 'Uncertain'
    response = client.post('/cases/email_1/review', json={'revision': case['revision'], 'category': 'SI_REQUEST'})
    assert response.json()['category'] == 'si_request'
    assert response.json()['status'] == 'complete'


def test_changed_source_invalidates_result_and_old_revision(api):
    client, runner, email = api
    original = client.get('/cases/email_1').json()
    email['body'] = 'Source email changed'
    assert client.get('/cases').json()[0]['status'] == 'pending'
    refreshed = client.get('/cases/email_1').json()
    assert refreshed['revision'] > original['revision']
    assert client.post('/cases/email_1/review', json={
        'revision': original['revision'], 'si': {'container_count': '10'}}).status_code == 409
    assert runner.call_count == 2


def test_confirming_comparison_category_resumes_pipeline(api):
    client, runner, _ = api
    runner.return_value = PipelineResult(email_id='email_1', category='GENERAL', status='NEEDS_REVIEW',
                                         review_reason='unreadable')
    case = client.get('/cases/email_1').json()
    runner.return_value = PipelineResult(email_id='email_1', category='BL_COMPARISON', status='NEEDS_REVIEW',
                                         review_reason='missing_attachment')
    response = client.post('/cases/email_1/review', json={'revision': case['revision'], 'category': 'BL_COMPARISON'})
    assert response.json()['category'] == 'bl_comparison'
    assert response.json()['status'] == 'review'
    assert runner.call_args.kwargs == {'category_override': 'BL_COMPARISON'}


def test_manual_attachment_classification_resolves_ambiguous_names(api):
    """A comparison request with vague attachment titles can't be auto-labeled
    SI vs BL; the reviewer must be able to assign them manually instead of
    looping back through the same failing rule-based resolution."""
    client, runner, _ = api
    runner.return_value = PipelineResult(email_id='email_1', category='BL_COMPARISON', status='NEEDS_REVIEW',
                                         review_reason='missing_attachment')
    case = client.get('/cases/email_1').json()
    assert case['reviewReasonCode'] == 'missing_attachment'
    assert case['siFile'] is None and case['blFile'] is None
    si = ExtractedDoc(attachment_path='attachments/si.txt', fields={
        key: FieldValue(value='10' if key in ['container_count', 'gross_weight_kg'] else 'ACME') for key in FIELDS})
    bl = si.model_copy(deep=True)
    bl.attachment_path = 'attachments/bl.txt'
    runner.return_value = PipelineResult(email_id='email_1', category='BL_COMPARISON', status='OK', si=si, bl=bl)
    response = client.post('/cases/email_1/review', json={
        'revision': case['revision'], 'si_attachment': 'attachments/si.txt', 'bl_attachment': 'attachments/bl.txt'})
    assert response.status_code == 200, response.text
    reviewed = response.json()
    assert reviewed['status'] == 'complete'
    assert reviewed['siFile'] == 'attachments/si.txt'
    assert reviewed['blFile'] == 'attachments/bl.txt'
    assert runner.call_args.kwargs == {'attachment_override': ('attachments/si.txt', 'attachments/bl.txt')}


def test_manual_attachment_classification_rejects_invalid_selection(api):
    client, runner, _ = api
    runner.return_value = PipelineResult(email_id='email_1', category='BL_COMPARISON', status='NEEDS_REVIEW',
                                         review_reason='wrong_doc_type')
    case = client.get('/cases/email_1').json()
    same_file = client.post('/cases/email_1/review', json={
        'revision': case['revision'], 'si_attachment': 'attachments/si.txt', 'bl_attachment': 'attachments/si.txt'})
    assert same_file.status_code == 422
    unknown_file = client.post('/cases/email_1/review', json={
        'revision': case['revision'], 'si_attachment': 'attachments/si.txt', 'bl_attachment': 'attachments/missing.txt'})
    assert unknown_file.status_code == 422
    only_one = client.post('/cases/email_1/review', json={
        'revision': case['revision'], 'si_attachment': 'attachments/si.txt'})
    assert only_one.status_code == 422
    assert client.get('/cases/email_1').json()['status'] == 'review'


def test_manual_case_is_created_pending_and_processed(api):
    client, runner, _ = api
    response = client.post('/cases', data={'subject': 'New shipment query', 'content': 'Please compare docs'},
                           files=[('files', ('SI.txt', b'shipping instruction', 'text/plain')),
                                  ('files', ('draft_BL.txt', b'bill of lading', 'text/plain'))])
    assert response.status_code == 201, response.text
    created = response.json()
    assert created['status'] == 'pending'
    assert created['subject'] == 'New shipment query'
    assert len(created['attachments']) == 2
    runner.assert_not_called()

    listed = client.get('/cases').json()
    assert listed[0]['id'] == created['id']

    processed = client.post(f"/cases/{created['id']}/process").json()
    assert runner.call_count == 1
    assert processed['status'] == 'review'  # default mocked pipeline result needs review
    # Idempotent: a second call reuses the cached result.
    client.post(f"/cases/{created['id']}/process")
    assert runner.call_count == 1


def test_manual_case_requires_some_content(api):
    client, _, _ = api
    assert client.post('/cases', data={'subject': '', 'content': ''}).status_code == 422


def test_manual_attachment_round_trips(api):
    client, _, _ = api
    created = client.post('/cases', data={'subject': 'Docs', 'content': ''},
                          files=[('files', ('SI.txt', b'hello world', 'text/plain'))]).json()
    assert created['attachments'][0]['path'] == f"manual/{created['id']}/SI.txt"
    download = client.get(created['attachments'][0]['download_url'])
    assert download.status_code == 200
    assert download.content == b'hello world'
    assert 'SI.txt' in download.headers['content-disposition']


@pytest.mark.parametrize('filename,content', [
    ('../../etc/passwd', b'data'),
    ('bad.exe', b'data'),
    ('fake.pdf', b'not a pdf'),
    ('bad.txt', b'has\x00null'),
])
def test_manual_upload_rejects_unsafe_files(api, filename, content):
    client, _, _ = api
    before = [case['id'] for case in client.get('/cases').json()]
    response = client.post('/cases', data={'subject': 'Docs', 'content': ''},
                           files=[('files', (filename, content, 'application/octet-stream'))])
    assert response.status_code == 422
    assert [case['id'] for case in client.get('/cases').json()] == before


def test_manual_upload_rejects_too_many_or_oversized_files(api):
    client, _, _ = api
    many = [('files', (f'file{i}.txt', b'x', 'text/plain')) for i in range(11)]
    assert client.post('/cases', data={'subject': 'Docs'}, files=many).status_code == 422
    huge = [('files', ('big.txt', b'x' * (10 * 1024 * 1024 + 1), 'text/plain'))]
    assert client.post('/cases', data={'subject': 'Docs'}, files=huge).status_code == 413


def test_manual_upload_rejects_duplicate_names(api):
    client, _, _ = api
    files = [('files', ('SI.txt', b'a', 'text/plain')), ('files', ('si.txt', b'b', 'text/plain'))]
    assert client.post('/cases', data={'subject': 'Docs'}, files=files).status_code == 422


def test_manual_attachment_path_is_scoped_to_its_case(api, monkeypatch):
    """A record whose declared email_id doesn't match the owner id embedded
    in its own attachment path (i.e. a forged/corrupted record) must not
    be able to read another case's files."""
    client, _, _ = api
    owner = client.post('/cases', data={'subject': 'A'}, files=[('files', ('SI.txt', b'secret', 'text/plain'))]).json()
    imposter_id = 'manual_' + 'f' * 12
    monkeypatch.setattr(web.MANUAL, 'emails', lambda: [
        {'email_id': imposter_id, 'from': 'x', 'to': [], 'subject': 'X', 'body': '',
         'attachments': [f"manual/{owner['id']}/SI.txt"], 'received_at': ''}])
    response = client.get(f'/emails/{imposter_id}/attachments/0')
    assert response.status_code == 400


def test_gmail_settings_default_state(api):
    client, _, _ = api
    assert client.get('/settings/gmail').json() == {
        'address': None, 'configured': False, 'enabled': False,
        'last_poll_at': None, 'last_error': None, 'ingested_count': 0}


def test_gmail_settings_rejects_invalid_address(api):
    client, _, _ = api
    response = client.put('/settings/gmail', json={'address': 'not-an-email', 'password': 'app-password-123'})
    assert response.status_code == 422


def test_gmail_settings_requires_password_on_first_save(api):
    client, _, _ = api
    response = client.put('/settings/gmail', json={'address': 'ops@example.com'})
    assert response.status_code == 422


def test_gmail_settings_save_never_returns_password(api):
    client, _, _ = api
    response = client.put('/settings/gmail', json={
        'address': 'ops@example.com', 'password': 'app-password-123', 'enabled': True})
    assert response.status_code == 200
    body = response.json()
    assert body == {'address': 'ops@example.com', 'configured': True, 'enabled': True,
                    'last_poll_at': None, 'last_error': None, 'ingested_count': 0}
    assert 'password' not in body
    # Re-saving without a password keeps the previously stored one.
    again = client.put('/settings/gmail', json={'address': 'ops@example.com', 'enabled': False})
    assert again.status_code == 200
    assert again.json()['configured'] is True
    assert again.json()['enabled'] is False


def test_enabling_and_disabling_settings_controls_poller(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setenv('AVERIS_GMAIL_POLL', '1')
    instances = []

    class FakePoller:
        def __init__(self, *_args, **_kwargs):
            self.running = False
            instances.append(self)

        def start(self):
            self.running = True
            return True

        def stop(self):
            self.running = False
            return True

    monkeypatch.setattr(web, 'GmailPoller', FakePoller)
    enabled = client.put('/settings/gmail', json={
        'address': 'ops@example.com', 'password': 'app-password-123', 'enabled': True})
    assert enabled.status_code == 200
    assert instances and instances[0].running is True

    # Saving corrected credentials while enabled must replace a poller that
    # may be sleeping in authentication backoff.
    enabled_again = client.put('/settings/gmail', json={
        'address': 'ops@example.com', 'password': 'corrected-password', 'enabled': True})
    assert enabled_again.status_code == 200
    assert len(instances) == 2
    assert instances[0].running is False
    assert instances[1].running is True

    disabled = client.put('/settings/gmail', json={'address': 'ops@example.com', 'enabled': False})
    assert disabled.status_code == 200
    assert instances[1].running is False


def test_gmail_settings_delete_clears_configuration(api):
    client, _, _ = api
    client.put('/settings/gmail', json={'address': 'ops@example.com', 'password': 'app-password-123'})
    response = client.delete('/settings/gmail')
    assert response.status_code == 200
    assert response.json()['configured'] is False


def test_gmail_settings_rejects_unknown_fields(api):
    client, _, _ = api
    response = client.put('/settings/gmail', json={
        'address': 'ops@example.com', 'password': 'app-password-123', 'unexpected': 'x'})
    assert response.status_code == 422


def test_gmail_test_connection_requires_credentials(api):
    client, _, _ = api
    assert client.post('/settings/gmail/test', json={}).status_code == 422


def test_gmail_test_connection_success(api, monkeypatch):
    client, _, _ = api
    login = Mock()
    monkeypatch.setattr(web, 'test_login', login)
    response = client.post('/settings/gmail/test', json={'address': 'ops@example.com', 'password': 'pw'})
    assert response.status_code == 200
    assert response.json() == {'ok': True}
    login.assert_called_once_with('ops@example.com', 'pw')


def test_gmail_test_connection_removes_display_spaces(api, monkeypatch):
    client, _, _ = api
    login = Mock()
    monkeypatch.setattr(web, 'test_login', login)
    response = client.post('/settings/gmail/test', json={
        'address': 'ops@example.com', 'password': 'abcd efgh ijkl mnop'})
    assert response.status_code == 200
    login.assert_called_once_with('ops@example.com', 'abcdefghijklmnop')


def test_gmail_test_connection_reuses_stored_credentials(api, monkeypatch):
    client, _, _ = api
    client.put('/settings/gmail', json={'address': 'ops@example.com', 'password': 'stored-pw'})
    login = Mock()
    monkeypatch.setattr(web, 'test_login', login)
    assert client.post('/settings/gmail/test', json={}).status_code == 200
    login.assert_called_once_with('ops@example.com', 'stored-pw')


def test_gmail_test_connection_surfaces_auth_failure(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(web, 'test_login', Mock(side_effect=GmailAuthError('bad credentials')))
    response = client.post('/settings/gmail/test', json={'address': 'ops@example.com', 'password': 'wrong'})
    assert response.status_code == 401


def test_gmail_test_connection_surfaces_network_failure(api, monkeypatch):
    client, _, _ = api
    monkeypatch.setattr(web, 'test_login', Mock(side_effect=GmailConnectionError('timed out')))
    response = client.post('/settings/gmail/test', json={'address': 'ops@example.com', 'password': 'pw'})
    assert response.status_code == 503


def test_gmail_ingested_mail_is_listed_processed_and_downloadable(api):
    """End-to-end through the real GmailStore (not the pipeline mock's
    email, which stays inbox-only): a record ingested the way the poller
    will ingest it must appear in /cases ahead of the static inbox record,
    process through the real pipeline mock, and serve its attachment."""
    client, runner, _ = api
    record = web.GMAIL_STORE.ingest({
        'email_id': 'gmail_1001_5', 'from': 'shipper@example.com', 'to': 'ops@example.com',
        'subject': 'New booking', 'body': 'See attached SI.', 'received_at': '2026-09-22T00:00:00+00:00',
        'source': 'gmail', 'message_id': '<x@mail.gmail.com>', 'gmail_uid': 5, 'gmail_uidvalidity': 1001,
    }, [('SI_new.pdf', b'%PDF-fake-si')])
    assert record['attachments'] == ['gmail/gmail_1001_5/SI_new.pdf']

    listed = client.get('/cases').json()
    ids = [case['id'] for case in listed]
    assert 'gmail_1001_5' in ids
    assert ids.index('gmail_1001_5') < ids.index('email_1')  # gmail ahead of the static inbox

    detail = client.get('/cases/gmail_1001_5').json()
    assert detail['subject'] == 'New booking'
    assert runner.call_count == 1

    download = client.get('/emails/gmail_1001_5/attachments/0')
    assert download.status_code == 200
    assert download.content == b'%PDF-fake-si'
