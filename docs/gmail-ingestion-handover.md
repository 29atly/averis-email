# Gmail ingestion — handover into Phase 2 (poller)

Status as of 2026-09-22: **Phases 0 and 1 are done and merged into the working tree
(uncommitted).** Phase 2 (the background poller that actually calls the fetch layer on
a schedule) has not been started. This doc is what the next person needs to pick it up
without re-deriving Phases 0–1.

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
5. **SSE for live UI updates** (Phase 3, not yet built) — not WebSocket. One-way
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

## What exists now (Phases 0–1)

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
existing pipeline + UI (unchanged)
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
| `src/averis_email/manual_store.py` | Gained two shared helpers used by both `ManualStore` and `GmailStore`: `list_records(root, id_re)` and `resolve_prefixed_path(root, prefix, email_id, path)`. `CompositeLoader` now takes an optional third `gmail=` store. |
| `src/averis_email/web.py` | `GMAIL_STORE` and `GMAIL_SETTINGS` singletons; `emails()` merges `manual + gmail + records`; `/settings/gmail` (GET/PUT/DELETE) + `/settings/gmail/test` (POST) endpoints; attachment download route handles the `gmail/` path prefix. |

### API surface already built (Phase 0)

- `GET /settings/gmail` → `{address, configured, enabled, last_poll_at, last_error, ingested_count}` — **never the password**.
- `PUT /settings/gmail` `{address, password?, enabled?}` — omitting `password` keeps the stored one; first save requires one. 422 on invalid address or blank password.
- `DELETE /settings/gmail` — clears everything, including the UID checkpoint.
- `POST /settings/gmail/test` `{address?, password?}` — synchronous IMAP login test; falls back to stored credentials for any field left blank. 401 on `GmailAuthError`, 503 on `GmailConnectionError`.

### Tests

33 tests across `tests/test_settings_store.py`, `tests/test_gmail_mime.py`,
`tests/test_gmail_client.py`, `tests/test_gmail_store.py`, plus additions to
`tests/test_web_api.py` (settings endpoints + one full ingest→list→process→download
end-to-end test using the real `GmailStore`). Full suite: `.venv/bin/python -m pytest
tests/ -q --ignore=tests/read_pdf_examples.py` → 200 passed, 1 pre-existing skip.

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

## Phase 2 scope: the poller

Not yet built. New file: `src/averis_email/gmail_poller.py`.

### Required behavior

1. **A pure, single-cycle function** — e.g. `run_once(settings, store)` — that:
   - Reads `settings.get()`.
   - If not `enabled` or no `address`/`password`: no-op, return.
   - If `last_uid is None` (never baselined) **or** a fresh `mailbox_status()` call
     returns a different `uidvalidity` than stored: call `mailbox_status()`, set
     `last_uid = uidnext - 1`, store the new `uidvalidity`, and **return without
     ingesting** — this is the baseline step from decision 3 above ("all new mail
     since enabled", not a backfill of the whole mailbox).
   - Otherwise call `fetch_since(address, password, last_uid)`. For each
     `(uid, raw, reason)` in ascending order:
     - If `raw is not None`: `gmail_mime.parse_message(raw, uid, uidvalidity)`, then
       `store.ingest(record, attachments)`.
     - Either way (including a skipped/oversized message), advance
       `last_uid = uid` and persist via `settings.set_sync_state(last_uid=uid, ...)`
       **before** moving to the next UID — this is what makes a mid-cycle crash safe
       (re-fetches at most one message; `GmailStore.ingest` is idempotent so a re-fetch
       of an already-ingested UID is a no-op).
   - On success, update `last_poll_at`, clear `last_error`, bump `ingested_count`.
   - On `GmailAuthError`/`GmailConnectionError`, set `last_error` and let the caller
     (the thread loop) decide backoff — this function should not sleep or retry itself.
2. **The thread loop** wraps `run_once` in a daemon thread started from a FastAPI
   `lifespan` handler in `web.py`, sleeping via `stop_event.wait(interval)` so shutdown
   is immediate and cycles never overlap.
   - **Gate startup** on both an env flag (e.g. `AVERIS_GMAIL_POLL != '0'`) and
     `settings.get()['enabled']` — `tests/test_web_api.py`'s `api` fixture uses `with
     TestClient(web.app) as client`, which fires `lifespan`. If the poller starts
     unconditionally, every existing test will try a real IMAP connection. Check this
     by running the full suite after wiring the lifespan hook — it must still show 200
     passed with **zero** network calls.
   - **Never hold `web.LOCK` across IMAP I/O.** A stalled socket would freeze every
     HTTP request. The atomic-rename writes in `GmailStore.ingest` and
     `GmailSettingsStore._write` are already safe without it.
   - **Backoff on error:** auth failure → 60s → 1h (Gmail locks accounts after repeated
     bad logins); network failure → 60s → 300s. Reset to 60s on the next success.
3. Cap poll-to-poll work using the existing `gmail_client.MAX_MESSAGES_PER_POLL=20` —
   a mailbox with a large backlog drains over several cycles rather than one huge
   synchronous fetch.

### Suggested test approach

Test `run_once` directly and exhaustively (baseline-on-first-run, baseline-on-
uidvalidity-change, normal ingest advancing the checkpoint, a message that fails MIME
parsing, the crash-safety property — call `run_once` twice with the same fake mailbox
state and confirm no duplicate `GmailStore` record). Monkeypatch
`gmail_client.mailbox_status`/`fetch_since` the same way `test_web_api.py` already
monkeypatches `web.test_login`. Do **not** try to test the thread/lifespan wrapper with
real timing — assert it starts/stops by checking a `stop_event` or a thread-alive flag,
with the loop body's single iteration exercised via `run_once` directly.

### Known follow-ups (from the original plan, not blocking Phase 2 but worth flagging)

- `STORE.namespace = INBOX.source` (`web.py`) means changing `AVERIS_INBOX_SOURCE`
  would invalidate every cached Gmail case too — not yet fixed, low priority until it
  bites someone.
- `emails()` re-reads every record from disk on every request; fine at hackathon scale,
  will need an mtime-keyed cache or a SQLite-backed listing once a live mailbox grows
  past a few thousand messages (Phase 5 in the original plan).
- Phase 3 (SSE live updates) and Phase 4 (frontend Settings page) still don't exist —
  Phase 2 only makes ingested mail visible after a manual page reload, same as every
  other list in this app today.

## Heads-up: unrelated concurrent work

While Phases 0–1 were being built, an **unrelated** in-progress change appeared in the
working tree — an `attachment_override` parameter added to `run_pipeline`
(`orchestrator.py`) and threaded through `process()` in `web.py`, plus changes to
`tests/test_review_context.py`. This was not part of the Gmail work and nothing here
depends on it, but it means `web.py` and `orchestrator.py` may look different from what
this doc describes by the time Phase 2 starts — diff against the actual files, not
just this doc, before editing them.
