"""API contract tests; pipeline inference is stubbed, routing and storage are real."""
from copy import deepcopy
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from averis_email import web
from averis_email.schemas import FIELDS, ExtractedDoc, FieldValue, PipelineResult
from averis_email.ui_api import StateStore


@pytest.fixture
def api(tmp_path, monkeypatch):
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
