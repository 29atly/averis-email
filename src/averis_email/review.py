"""Original source context shared by all email review outcomes."""
from copy import deepcopy
from urllib.parse import quote

from averis_email.schemas import ReviewAttachment, ReviewContext


def review_context(email: dict, stage: str) -> ReviewContext:
    paths = email.get("attachments")
    attachments = []
    if isinstance(paths, list):
        for index, path in enumerate(paths):
            if isinstance(path, str) and path.strip():
                attachments.append(ReviewAttachment(
                    path=path,
                    download_url=f"/emails/{quote(str(email['email_id']), safe='')}/attachments/{index}",
                ))
    return ReviewContext(stage=stage, original_email=deepcopy(email), attachments=attachments)
