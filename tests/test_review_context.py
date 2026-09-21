from copy import deepcopy
from unittest.mock import Mock, patch

import pytest
from fastapi import HTTPException

from averis_email.classifier import ClassificationDecision
from averis_email.orchestrator import run_pipeline
from averis_email.schemas import AttachmentResolutionResult, ExtractedDoc
from averis_email.stages.formatting import build_report
from averis_email import web


EMAIL = {'email_id': 'review_1', 'from': 'sender@example.com',
         'subject': 'Please check BL', 'body': 'Original message\nwith context.',
         'attachments': ['attachments/original.pdf', 'attachments/instructions.txt']}


@pytest.mark.parametrize('failure,stage', [
    ('classification_exception', 'classification'), ('classification_review', 'classification'),
    ('resolution_exception', 'attachment_resolution'), ('resolution_review', 'attachment_resolution'),
    ('missing_attachment', 'attachment_resolution'), ('extraction_exception', 'extraction'),
    ('unreadable', 'extraction'), ('missing_fields', 'validation'),
    ('validation_exception', 'validation'), ('comparison_exception', 'comparison'),
])
def test_every_review_exit_preserves_sources(failure, stage):
    email = deepcopy(EMAIL)
    si = ExtractedDoc(attachment_path=email['attachments'][1])
    bl = ExtractedDoc(attachment_path=email['attachments'][0])
    resolution = AttachmentResolutionResult(si_path=si.attachment_path, bl_path=bl.attachment_path,
                                           si_doc=si, bl_doc=bl)
    with patch('averis_email.orchestrator.classify_email', return_value=ClassificationDecision('BL_COMPARISON')) as classify, \
         patch('averis_email.orchestrator.classification.find_si_bl', return_value=resolution) as resolve, \
         patch('averis_email.orchestrator.extraction.extract_fields', side_effect=lambda doc: doc) as extract, \
         patch('averis_email.orchestrator.validation.missing_fields', return_value=[]) as validate, \
         patch('averis_email.orchestrator.comparison.compare_fields', return_value=([], {})) as compare:
        if failure == 'classification_exception': classify.side_effect = RuntimeError('failed')
        if failure == 'classification_review': classify.return_value = ClassificationDecision(None, True)
        if failure == 'resolution_exception': resolve.side_effect = RuntimeError('failed')
        if failure == 'resolution_review': resolution.review_required = True
        if failure == 'missing_attachment': resolution.si_path = None
        if failure == 'extraction_exception': extract.side_effect = RuntimeError('failed')
        if failure == 'unreadable': si.readable = False
        if failure == 'missing_fields': validate.return_value = ['shipper']
        if failure == 'validation_exception': validate.side_effect = RuntimeError('failed')
        if failure == 'comparison_exception': compare.side_effect = RuntimeError('failed')
        result = run_pipeline(None, email)
    assert result.status == 'NEEDS_REVIEW'
    assert result.review_context.stage == stage
    assert result.review_context.original_email == EMAIL
    assert [a.path for a in result.review_context.attachments] == EMAIL['attachments']
    assert result.review_context.attachments[0].download_url == '/emails/review_1/attachments/0'
    email['attachments'].clear()
    assert result.review_context.original_email == EMAIL
    assert 'review_context' not in result.to_submission_entry()
    assert result.model_dump(mode='json')['review_context']['original_email'] == EMAIL
    report = build_report([result])
    assert 'NEEDS_REVIEW: 1' in report
    assert 'Original message' in report
    assert f'Stage: {stage}' in report


def test_attachment_override_skips_reclassification():
    """A reviewer assigning SI/BL roles by hand has already confirmed this is
    a comparison request. Re-deriving the category (which can call out to a
    non-deterministic LLM/Laya backend) must not happen -- doing so risks the
    case abstaining again and bouncing the reviewer back to square one."""
    email = deepcopy(EMAIL)
    si = ExtractedDoc(attachment_path='attachments/si.txt')
    bl = ExtractedDoc(attachment_path='attachments/bl.txt')
    with patch('averis_email.orchestrator.classify_email') as classify, \
         patch('averis_email.orchestrator.classification.find_si_bl') as resolve, \
         patch('averis_email.orchestrator.ingestion.read_document',
               side_effect=lambda loader, path: si if path == 'attachments/si.txt' else bl), \
         patch('averis_email.orchestrator.extraction.extract_fields', side_effect=lambda doc: doc), \
         patch('averis_email.orchestrator.validation.missing_fields', return_value=[]), \
         patch('averis_email.orchestrator.comparison.compare_fields', return_value=([], {})):
        result = run_pipeline(None, email, attachment_override=('attachments/si.txt', 'attachments/bl.txt'))
    classify.assert_not_called()
    resolve.assert_not_called()
    assert result.category == 'BL_COMPARISON'
    assert result.status == 'OK'
    assert result.si.attachment_path == 'attachments/si.txt'
    assert result.bl.attachment_path == 'attachments/bl.txt'


def test_download_returns_exact_original_bytes(tmp_path):
    folder = tmp_path / 'attachments'
    folder.mkdir()
    raw = b'%PDF\x00\xffunreadable original'
    (folder / 'original.pdf').write_bytes(raw)
    inbox = web.Inbox(str(tmp_path))
    with patch.object(web, 'INBOX', inbox), patch.object(inbox, 'emails', return_value=[EMAIL]):
        response = web.get_original_attachment('review_1', 0)
        assert response.body == raw
        assert 'attachment;' in response.headers['content-disposition']
        with pytest.raises(HTTPException):
            web.get_original_attachment('review_1', 1)
        with pytest.raises(HTTPException):
            web.get_original_attachment('other', 0)
        with pytest.raises(HTTPException):
            web.get_original_attachment('review_1', -1)


@pytest.mark.parametrize('path', ['../private.txt', '/private.txt', 'attachments/../../private.txt',
                                  'attachments/%2e%2e/private.txt'])
def test_download_rejects_unsafe_references(path):
    inbox = Mock(is_http=True)
    inbox.emails.return_value = [{**EMAIL, 'attachments': [path]}]
    with patch.object(web, 'INBOX', inbox), pytest.raises(HTTPException):
        web.get_original_attachment('review_1', 0)
    inbox.read_bytes.assert_not_called()
