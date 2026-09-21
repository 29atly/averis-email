# Gmail ingestion — live inbox implementation

Status as of 2026-09-22: **Phases 0–4 are implemented.** The IMAP transport, MIME
parser, durable stores, scheduled poller, server-sent live updates, and Gmail Settings
UI are connected. New inbox messages received after the mailbox is enabled appear as
pending work-queue cases without importing the mailbox's historical backlog.

## Why this feature exists

The app currently ingests mail from two places, merged in `web.py`'s `emails()`: the
static hackathon dataset (`Inbox`, `data_loader.py`) and manually composed uploads
(`ManualStore`, `manual_store.py`). Neither is a real mailbox. The goal is a dedicated
Gmail account whose inbox is pulled in automatically and run through the existing
pipeline, with the mailbox address/app password configurable from a Settings page,
running unattended on a VM.

## Decisions already made (do not re-litigate these)

1. **IMAP + App Password**, not the Gmail API. SMTP can't read a mailbox at all. The
   Gmail API's `gmail.readonly` is a *restricted* scope needing OAuth verification plus
   a CASA Tier 2 security audit for production — ruled out. IMAP needs zero new
   dependencies (stdlib `imaplib` + `email`).
2. **Poll every 60s, no IMAP IDLE.** IDLE would cut latency to seconds but needs the
   `imapclient` dependency (this Python's `imaplib` has no built-in IDLE), a 29-minute
   renewal cycle, and reconnect/backoff logic — deferred until 60s latency is proven
   insufficient.
3. **Ingest all new INBOX mail** (not just mail with attachments), tracked by IMAP UID
   so nothing is reprocessed. No sender allowlist (yet).
4. **Ingested mail is left `pending`, not processed by the poller.** OCR/LLM extraction
   takes tens of seconds; running it inside the poller (single uvicorn worker) would
   stall every HTTP request. The existing "open case to process" and bulk-process UI
   paths already handle pending cases — Phase 2 only needs to make new mail *appear*.
5. **SSE for live UI updates** (implemented in Phase 3) — not WebSocket. One-way
   server→client fits, `EventSource` auto-reconnects, no new dependency.
6. **Auth / VM network hardening is explicitly out of scope** for this whole feature.
   The API has no authentication and CORS is `*`. This matters more once a
   credential-writing endpoint exists (it now does — see below). Minimum mitigation if
   this ships to a real VM before auth is addressed: bind uvicorn to `127.0.0.1` and
   reach it over SSH.

The original complexity/design research (SMTP vs IMAP, OAuth verification findings,
poller architecture options) lives in the approved plan file used to build this,
`~/.claude/plans/ticklish-snacking-adleman.md` on the machine this was built on — it is
**not** in the repo, so treat this doc as the source of truth going forward instead of
chasing that path down.

## What exists now (Phases 0–4)

```
IMAP (Gmail)
    |
    v
gmail_client.py        -- pure IMAP transport (login, STATUS, UID SEARCH/FETCH)
    |  raw RFC822 bytes
    v
gmail_mime.py           -- pure MIME parsing (raw bytes -> email dict + attachments)
    |  (record, [(filename, bytes), ...])
    v
gmail_store.py           -- disk persistence (GmailStore, sibling of ManualStore)
    |  record written once, read back verbatim
    v
web.py: emails() / CompositeLoader / attachment download route
    |
    v
existing pipeline + UI

gmail_poller.py          -- 60s background cycle, UID checkpoint, bounded backoff
    |
    v
web.py: /events (SSE) --> browser work-queue refresh
```

Settings (mailbox address, app password, enabled flag, **and the UID sync
checkpoint**) live in `settings_store.py` / `GmailSettingsStore`, a single JSON file
(`AVERIS_GMAIL_CONFIG`, default `.cache/gmail-config.json`), file mode 0600.

### File inventory

| File | Responsibility |
|---|---|
| `src/averis_email/settings_store.py` | `GmailSettingsStore`: address/password/enabled + `uidvalidity`/`last_uid`/`last_poll_at`/`last_error`/`ingested_count`. `.get()` (internal, includes password), `.public()` (API-safe, no password), `.save()`, `.clear()`, `.set_sync_state(**fields)` (poller-only, preserves credentials). |
| `src/averis_email/gmail_client.py` | `connect`/`test_login` (Phase 0), `mailbox_status(address, password)` → `(uidvalidity, uidnext)`, `fetch_since(address, password, since_uid)` → `(uidvalidity, [(uid, raw_bytes_or_None, skipped_reason_or_None), ...])`. Read-only (`EXAMINE`), capped at `MAX_MESSAGES_PER_POLL=20` per call, skips messages over `MAX_MESSAGE_BYTES=30MB` without blocking the checkpoint. Raises `GmailAuthError` vs `GmailConnectionError` — the poller must treat these differently (see Backoff below). |
| `src/averis_email/gmail_mime.py` | `parse_message(raw, uid, uidvalidity)` → `(record, attachments)`. Pure function, no I/O. `record['email_id']` is `gmail_{uidvalidity}_{uid}`. |
| `src/averis_email/gmail_store.py` | `GmailStore.ingest(record, attachments)` — idempotent on `email_id` (safe to call twice with the same UID after a crash), skips invalid attachments while keeping the message, writes atomically. `.emails()`, `.read_bytes()`, `.resolve()` for the existing loader/download contract. |
| `src/averis_email/gmail_poller.py` | `run_once(settings, store)` performs one testable synchronization cycle. `GmailPoller` owns the daemon thread, immediate shutdown, and authentication/network backoff. |
| `src/averis_email/manual_store.py` | Gained two shared helpers used by both `ManualStore` and `GmailStore`: `list_records(root, id_re)` and `resolve_prefixed_path(root, prefix, email_id, path)`. `CompositeLoader` now takes an optional third `gmail=` store. |
| `src/averis_email/web.py` | Gmail stores/settings, poller lifespan management, merged email listing, settings endpoints, attachment downloads, and `/events` SSE updates. |
| `frontend/settings.html`, `frontend/settings.js` | User-facing Gmail address/app-password setup, connection testing, enable/disable, removal, and synchronization status. |

### API surface already built (Phase 0)

- `GET /settings/gmail` → `{address, configured, enabled, last_poll_at, last_error, ingested_count}` — **never the password**.
- `PUT /settings/gmail` `{address, password?, enabled?}` — omitting `password` keeps the stored one; first save requires one. 422 on invalid address or blank password.
- `DELETE /settings/gmail` — clears everything, including the UID checkpoint.
- `POST /settings/gmail/test` `{address?, password?}` — synchronous IMAP login test; falls back to stored credentials for any field left blank. 401 on `GmailAuthError`, 503 on `GmailConnectionError`.

### Tests

Tests cover settings, MIME parsing, IMAP behavior, disk persistence, poll cycles,
thread lifecycle, settings endpoints, and ingest→list→process→download integration.
Current verification: `.venv/bin/python -m pytest tests/ -q
--ignore=tests/read_pdf_examples.py` → 209 passed, 4 optional Laya skips, plus 118
subtests. `node --test tests/frontend_api.test.cjs` → 5 passed.

`tests/test_gmail_client.py` has a hand-rolled `FakeConn` that reproduces real
`imaplib` response shapes (tuple-vs-bytes items, the `UID N:*` RFC 3501 quirk). Reuse
this pattern rather than mocking `imaplib` calls individually — it's the only way to
catch response-parsing bugs before they hit a real mailbox.

**Gotcha:** don't `from averis_email.gmail_client import test_login` directly in a test
module — pytest collects any top-level `test_*` name it finds, including imported
ones, and will try to run Gmail's `test_login` as a test case. Import the module and
call `gmail_client.test_login(...)`, or alias on import (see
`test_gmail_client.py`'s `gmail_test_login` alias).

**Environment gotcha:** this repo's dependencies (including `python-multipart`, needed
just to import `web.py`) are in `.venv/`, not whatever `python3` resolves to on PATH.
Use `.venv/bin/python -m pytest ...`.

## Implemented polling behavior

- `run_once(settings, store)` is pure with respect to scheduling and is exhaustively
  unit tested.
- First enablement and UIDVALIDITY changes baseline to `UIDNEXT - 1` without a
  historical backfill.
- Later cycles fetch and persist new messages in UID order, checkpointing each one.
- Oversized and malformed messages are skipped without wedging the mailbox; storage
  failures do not advance the checkpoint.
- The daemon starts from FastAPI lifespan or when an enabled configuration is saved,
  and stops immediately when disabled, removed, or the application shuts down.
- Authentication failures back off from 60 seconds to one hour; network failures from
  60 seconds to five minutes. A successful cycle resets the backoff.
- `AVERIS_GMAIL_POLL=0` disables the thread; `AVERIS_GMAIL_POLL_INTERVAL` controls the
  successful-cycle interval (default 60 seconds).
- `/events` sends inbox changes to the frontend. The work queue refreshes when new
  messages arrive; the settings module refreshes connection status.

### Known follow-ups (from the original plan, not blocking Phase 2 but worth flagging)

- `STORE.namespace = INBOX.source` (`web.py`) means changing `AVERIS_INBOX_SOURCE`
  would invalidate every cached Gmail case too — not yet fixed, low priority until it
  bites someone.
- `emails()` re-reads every record from disk on every request; fine at hackathon scale,
  will need an mtime-keyed cache or a SQLite-backed listing once a live mailbox grows
  past a few thousand messages (Phase 5 in the original plan).
- Authentication/CORS hardening remains required before exposing the app to an
  untrusted network. The current hackathon deployment assumption is local access or an
  SSH tunnel.

## Heads-up: unrelated concurrent work

While Phases 0–1 were being built, an **unrelated** change was committed — an
`attachment_override` parameter added to `run_pipeline`
(`orchestrator.py`) and threaded through `process()` in `web.py`, plus changes to
`tests/test_review_context.py`. This was not part of the Gmail work and nothing here
depends on it, but it means `web.py` and `orchestrator.py` may look different from what
this doc describes by the time Phase 2 starts — diff against the actual files, not
just this doc, before editing them.
