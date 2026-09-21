"""Stage 1: classify incoming inbox records.

Owner: Email Intelligence teammate.

Contract
--------
classify_email(email: dict) -> str
    `email` is one inbox record (email_id/from/subject/body/attachments).
    Must return one of averis_email.schemas.CATEGORIES.

find_si_bl(email: dict) -> AttachmentResolutionResult
    Only called for emails already classified as BL_COMPARISON. Must
    explain what it found, not just hand back two paths:
      - si_path / bl_path: the resolved paths, or None if not found
      - review_required + review_reason: set True with a reason from
        schemas.REVIEW_REASONS ("missing_attachment", "wrong_doc_type",
        "unreadable", "missing_value") whenever the attachments can't be
        resolved safely
      - warnings: human-readable notes for the report/review UI, e.g.
        "2 BL candidates found: draft_bl_v1.pdf, draft_bl_v2.pdf"

The two functions below are placeholders (dumb heuristics) so the pipeline
runs end-to-end today. Replace the bodies with real logic -- keep the
signatures identical so nothing else in the codebase needs to change.

Person 2 rules: classify current email intent and resolve filename candidates.

Selected paths preserve identity, but do not prove document contents/readability.
"""
import re
from pathlib import PurePosixPath
from averis_email.schemas import AttachmentResolutionResult


def _normalize(text):
    """
    Normalize text before applying keyword/regex-based rules.
    Lowercase, replace underscores with spaces, collapse whitespace, and strip leading/trailing whitespace.
    """
    if not text:
        return None
    return re.sub(r'\s+', ' ', text.replace('_', ' ').lower()).strip()


def _current_body(body):
    """
    Extract and normalize the current message from an email thread.

    Email bodies may contain previous replies, forwarded messages,
    signatures, or quoted text. These older sections can contain
    keywords that do not represent the intent of the current email.

    This function therefore:
    - stops at common reply/forward/signature markers,
    - ignores quoted lines beginning with ``>``,
    - ignores common external-email warnings,
    - normalizes the remaining text.
    """
    lines = []
    for line in body.splitlines():
        line = line.strip()
        # Stop processing once the previous conversation or signature begins. This prevents old messages from affecting classification.
        if re.match(r'(?i)^(from:|on .+wrote:|[-_]{5,}|-+\s*(original|forwarded) message|best regards|kind regards|regards\b|sent from my)', line):
            break
        if line.startswith('>') or re.match(r'(?i)^(warning:.*originated outside|\[?external (email|sender))', line):
            continue
        lines.append(line)
    return _normalize(' '.join(lines))


def _intent(text):
    """
    Classify email intent using rule-based keyword patterns.

    The rules are evaluated in a specific order. More specific or
    high-priority categories are checked first so that incidental
    keywords do not override the main intent.

    Possible results include:
        - SPAM
        - GENERAL
        - SI_REQUEST
        - BL_COMPARISON
        - INVOICE_QUERY
        - None if no rule matches
    """
    if not text:
        return None
    # Detect common spam/scam patterns first.
    # Require the combined proposal, claimed bank role, and solicitation;
    # ordinary invoice payment/bank-detail correspondence is not enough.
    if (re.search(r'\bbank officer\b', text)
            and re.search(r'\burgent business proposal\b', text)
            and re.search(r'\b(?:reply|respond|send|provide|share)\b[^.!?]{0,80}\byour bank (?:details|information)\b', text)):
        return 'SPAM'
    if re.search(r'claim your.{0,30}gift card|monthly draw|package.{0,60}unpaid customs fee', text):
        return 'SPAM'
    if re.search(r'\b(lottery|viagra|you (?:have )?won|claim your prize|one weird trick)\b|mailbox.{0,60}(?:full|limit|exceeded)|verify your account.{0,80}(?:deactivation|suspend)|limited time offer|\bbuy now\b|\bparcel.{0,40}(?:fee|payment)', text):
        return 'SPAM'
    # Completion notices may contain vessel names between process and outcome.
    # Require success AND no action, and keep failures/questions/requests out.
    if (re.search(r'\bbilling process\b', text)
            and re.search(r'\bcompleted successfully\b', text)
            and re.search(r'\bno (?:further )?action (?:is )?required\b', text)
            and not re.search(r'\b(not|never|failed|failure|error|missing|disput\w*|wrong|incorrect|please|kindly|however)\b|\?', text)):
        return 'GENERAL'
    # Some operational/business emails are explicitly treated as GENERAL.
    if re.search(r'\b(berthing report|update summary|outstanding (?:bl|list)|holiday|delivery planning)\b|submit si\s*&\s*aed', text):
        return 'GENERAL'

    # Match common ways of referring to a Bill of Lading.
    bl = r'\b(?:b\s*/\s*l|bl|bill of lading)\b'
    # A new SI request may mention a future BL or invoices.
    # Check SI requests before BL comparison so these incidental mentions
    # do not incorrectly change the main email intent.
    if re.search(r'\b(?:please|kindly)\s+(?:find|prepare|create)\s+(?:the\s+|a\s+|new\s+)?shipping instructions?\b', text):
        return 'SI_REQUEST'
    # Detect BL comparison/review requests using an action word
    # such as check, compare, verify, confirm, amend, or review.
    if re.search(bl, text) and re.search(r'\b(check\w*|compar\w*|verif\w*|confirm\w*|amend\w*|discrepanc\w*|review\w*)\b', text):
        return 'BL_COMPARISON'
     # Detect other common BL/document review phrasings.
    if re.search(r'\bdraft\s+' + bl + '|' + bl + r'\s+draft\b|\b(?:confirm|check|compare|verify)\s+(?:the\s+)?(?:docs|documents)\b', text):
        return 'BL_COMPARISON'
     # Detect invoice and billing-related requests.
    if re.search(r'\b(invoice|billing|local charges|total freight|detention charges)\b|\bd\s*&\s*d\b', text):
        return 'INVOICE_QUERY'
    # Detect SI requests using SI-related terms together with
    # request/action words.
    if re.search(r'\b(si|shipping instructions?)\b', text) and re.search(r'\b(request\w*|need\w*|prepar\w*|creat\w*|send|submit|find|attached|cust|new)\b', text):
        return 'SI_REQUEST'
    # Detect reply/forward subjects that begin with an SI reference.
    if re.match(r'^(?:(?:re|fw|fwd)\s*[: -]\s*)*si\s*-', text):
        return 'SI_REQUEST'

    # Detect reply/forward subjects that begin with an SI reference.
    return None


def match_email_rules(email: dict) -> str | None:
    """Return a matched intent, or None so another classifier can try."""
    return (_intent(_current_body(email.get('body') or ''))
            or _intent(_normalize(email.get('subject') or '')))


def classify_email(email: dict) -> str:
    """Classify the intent of an incoming email.

    Classification prioritizes the current email body and then falls
    back to the subject. Attachments are deliberately ignored because
    their filenames should not determine the email's intent.
    """
    return match_email_rules(email) or 'GENERAL'


def _filename_text(path):
    """Normalize the basename for matching without altering the source path."""
    # Extract only the filename without its directory or extension.
    stem = PurePosixPath(path.replace('\\', '/')).stem
    # Add spaces between common camel-case patterns.
    stem = re.sub(r'([a-z])([A-Z])', r'\1 \2', stem)
    stem = re.sub(r'([A-Z])([A-Z][a-z])', r'\1 \2', stem)
    # Convert punctuation/separators to spaces and normalize case.
    return re.sub(r'[^a-z0-9]+', ' ', stem.lower())


def _filename_roles(path):
    """Infer candidate roles from the filename, not document contents."""
    name = _filename_text(path)
    roles = set()
    # Identify filenames that look like Shipping Instructions.
    if re.search(r'\bsi(?:\d+)?\b|\bshipping\s*instructions?\b', name):
        roles.add('SI')
    # Identify filenames that look like Bill of Lading.
    if re.search(r'\b(?:draft\s*)?bl(?:\d+)?\b|\bb\s+l\b|\bbill\s*of\s*lading\b', name):
        roles.add('BL')

    return roles


def find_si_bl(email: dict) -> AttachmentResolutionResult:
    """Resolve SI and BL attachment candidates using filenames.

    The function does not open or inspect the actual documents.
    It only uses attachment filenames to identify candidates.

    A role is resolved only when exactly one candidate exists.
    Missing or ambiguous candidates are sent for human review rather
    than being guessed.
    """
    attachments = email.get('attachments') or []
    # Validate the attachment structure before processing it.
    if not isinstance(attachments, list):
        return AttachmentResolutionResult(review_required=True, review_reason='missing_attachment',
                                          warnings=['attachments must be a list of paths'])
    # Store all possible SI and BL candidates separately.
    candidates = {'SI': [], 'BL': []}
    warnings, seen = [], set()
    ambiguous = False
    conflicting_type = False
    for path in attachments:
         # Ignore malformed or empty attachment paths.
        if not isinstance(path, str) or not path.strip():
            warnings.append('Ignored an invalid attachment path')
            continue
         # Ignore malformed or empty attachment paths.
        if path in seen:
            continue
        seen.add(path)
        # Determine whether the filename looks like an SI or BL.
        roles = _filename_roles(path)
        # Conflicting filename clues require review; this is not a content
        # verification. Keep the exact filename in warnings for the reviewer.
        if roles and re.search(r'\b(?:commercial\s*)?invoice\b|\bpacking\s*list\b|\bcertificate\s*of\s*origin\b', _filename_text(path)):
            conflicting_type = True
            warnings.append(f'Conflicting document-type clues in filename (content unverified): {path}')
            continue
         # A filename matching both roles is ambiguous and cannot
        # be safely resolved automatically.
        if len(roles) > 1:
            ambiguous = True
            warnings.append(f'Attachment names both SI and BL: {path}')
        # Add the filename to its identified candidate list.
        elif roles:
            candidates[next(iter(roles))].append(path)
         # Unknown filenames are not assumed to be either SI or BL.
        else:
            warnings.append(f'Unrecognized attachment role: {path}')
    resolved = {}
    for role, paths in candidates.items():
        # Resolve the role only when there is exactly one candidate.
        # Zero or multiple candidates are treated as unresolved.
        resolved[role] = paths[0] if len(paths) == 1 else None
        if not paths:
            warnings.append(f'No {role} attachment identified')
        elif len(paths) > 1:
            warnings.append(f'Multiple {role} candidates: {paths}')
    # Human review is required when: an attachment is ambiguous, SI could not be uniquely resolved, or BL could not be uniquely resolved.
    review = conflicting_type or ambiguous or not resolved['SI'] or not resolved['BL']
    reason = 'wrong_doc_type' if conflicting_type else 'missing_attachment'
    return AttachmentResolutionResult(si_path=resolved['SI'], bl_path=resolved['BL'],
        review_required=bool(review), review_reason=reason if review else None,
        warnings=warnings)
