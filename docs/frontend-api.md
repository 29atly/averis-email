# Frontend/API integration

The original frontend loaded seven hardcoded cases from `data.js`; it made no
HTTP calls. The original API exposed `/health`, a four-field `/emails` summary,
and a raw `PipelineResult` at `/emails/{email_id}`. Neither email response could
populate the existing UI directly.

## Endpoint audit and implementation

| Existing UI requirement | Original backend compatibility | Implemented contract |
| --- | --- | --- |
| Connection state | `/health` was usable as liveness only | Kept; UI displays connected only after fetching cases |
| Inbox, search, category/status filters, sidebar counts | `/emails` lacked category, status, body and date | `GET /cases?q=&category=&status=&limit=100&offset=0`; frontend loads pages and filters locally |
| Original message and recipient | `/emails/{id}` returned pipeline output without message metadata | `GET /cases/{id}` combines source email and stored pipeline result |
| Seven SI/BL field pairs | Existing `si.fields`, `bl.fields`, and `diff_detail` contained usable values in a different shape | `values[field] = [SI, BL]`, with raw values, server normalization, file/page/text and correction markers |
| Attachment cards/downloads | No download route | `GET /emails/{id}/attachments/{index}` returns the original attachment bytes |
| Human correction and continuation | No endpoint; browser altered SI values in local storage and marked complete | `POST /cases/{id}/review` validates separate SI/BL corrections and recomputes comparison |
| Uncertain classification | Backend returned `GENERAL` plus `NEEDS_REVIEW` | UI prioritizes review status; review accepts an explicit category, including BL processing |
| Retry | Toast only | `POST /cases/{id}/retry` runs the current pipeline synchronously |
| Activity history and metrics | Fabricated stages, time and evidence coverage | Case response includes stored processing/review/retry events, measured duration and actual evidence coverage |
| Empty/error states | UI assumed a populated demo inbox | Explicit empty screens and API errors; no automatic demo fallback |

The existing `/emails` response shape and submission fields are retained.
`/emails/{id}` now shares cached results and corrections with the UI; use the
retry endpoint to run again. Review results additionally include `review_context`
with the source email, attachment links and failing stage. This context is not
included in submission JSON.

## Run

From the repository root, install the project and start one API worker:

```bash
pip install -e .
AVERIS_INBOX_SOURCE='Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2' \
  uvicorn averis_email.web:app --reload --port 8000
```

Open **http://localhost:8000/ui/**. Interactive API contracts are at `/docs`.
`AVERIS_INBOX_SOURCE` accepts a bundle directory containing `inbox/` and
`attachments/`, or the organizer's HTTP inbox source. It defaults to `data`.
A missing local inbox returns 503 instead of silently displaying an empty list.

The existing classifier/extraction configuration still applies. Real processing
may require model dependencies or credentials. No model call occurs just from
listing the inbox. A message is `pending` / `unclassified` until it is first
opened; category filters, review counts and completed counts reflect processed
cases. Opening a case processes it once. Navigating between modules reuses its
stored result.

For a separate static frontend server, serve `frontend/` (not `dist/`). It uses
`http://localhost:8000` by default. To choose another backend, set
`window.AVERIS_API_URL` in a script before `data.js` on each page. Serving `/ui/`
uses the same origin automatically.

## Case fields

Each case includes `id`, `subject`, `sender`, `recipient`, `body`, `time`,
`receivedLabel`, lowercase `category`, `status` (`pending`, `review`, `complete`),
`attachments`, `siFile`, `blFile`, `values`, `defectFields`, `processingTime`,
`reviewFields`, `reviewReasonCode`, `reviewReason`, `reviewStage`, `error`,
`canConfirmValues`, `activity`, `evidenceCoverage`, and `revision`.

Attachments contain `name`, `path`, and a relative `download_url`. Downloads
resolve an index within the email's own attachment list and reject traversal,
encoded path references and local symlinks outside the attachments directory.

Each comparison field has two evidence objects:

```json
{
  "file_path": "attachments/email_004_SI.txt",
  "page_number": 1,
  "source_text": "Total Containers: 6 x 40'HC",
  "raw": "6 x 40'HC",
  "normalized": 6,
  "corrected": false
}
```

Unknown evidence remains null. Missing/placeholder values normalize to null.
Dates use the supplied `received_at`, `date`, or `timestamp`; recipients use
`to`. The current bundle does not provide dates or recipient headers, so these
are blank. No dates, recipients, pages, or source quotes are inferred. Coverage
counts fields with file, page and source text on **both** documents. Original
source snippets remain unchanged after correction; corrected values are marked.

## Review and retry

Submit the latest revision and corrections by document:

```http
POST /cases/email_517/review
Content-Type: application/json

{"revision": 1, "si": {"port_of_loading": "SINGAPORE", "port_of_discharge": "CALLAO, PERU"}, "bl": {}}
```

Only missing-value cases with readable SI and BL documents accept field
corrections. Every missing value on both documents must be resolved. Unknown
fields, unusable values, unexpected parameters and incomplete corrections return
422. Stale revisions or cases no longer awaiting review return 409. Recomparison
can correctly finish with a mismatch; review never assumes corrected values match.

For classification review, send `{"revision": 1, "category": "BL_COMPARISON"}`
(or another uppercase pipeline category). BL classification resumes document
processing; other categories finish classification. Category confirmation cannot
be mixed with field corrections or used when extracted documents already exist.

Retry accepts no body, returns the updated case, and discards manual corrections
in favor of fresh processing. Fix missing or unreadable attachments in the source
bundle before retrying. Uploads and replacement files are not implemented.

## State and scope

Results, corrections, revisions, measured durations and observed activity are
stored in SQLite at `AVERIS_UI_STATE` (default `.cache/ui-state.sqlite3`) and
survive server restarts. Changing source email metadata invalidates cached
results. Changing only attachment bytes, model settings or pipeline code requires
an explicit retry. State is scoped to the configured inbox source.

This is a local synchronous workflow: use one API worker. It does not expose a
background job queue, per-stage timing, authentication, or document-page image
rendering. Evidence displays real source snippets, not a simulated page preview.
The old static examples are retained in `frontend/demo-data.js` as a reference;
they are not loaded by the application.

## Verification

```bash
.venv/bin/pytest -q tests
node --test tests/frontend_api.test.cjs
```

API tests use the real FastAPI routes and SQLite storage with stubbed inference.
Frontend tests execute the actual scripts with a minimal DOM and mocked HTTP;
they do not replace a real-browser visual test.
