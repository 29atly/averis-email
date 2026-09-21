# Shipping Verification UI

The frontend is connected to the FastAPI backend. It includes the inbox, original
message and attachment downloads, seven-field SI/BL comparison, source evidence,
human review, retry and activity history.

From the work queue, **Compose email** opens a form for a manually written
subject, content and attachments (PDF, XLSX, TXT, DOCX); submitting persists it
and runs the pipeline, then returns to the queue with the new case at the top.
Each row also has a checkbox, with a header checkbox to select all currently
visible (filtered/searched) rows; selecting any row shows a bar to process just
the unprocessed ones in sequence, with live per-row progress and a stop control.

From the repository root:

```bash
AVERIS_INBOX_SOURCE='Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2' \
  uvicorn averis_email.web:app --reload --port 8000
```

Open **http://localhost:8000/ui/**. Configure the classifier and extraction
credentials/dependencies as described in the main README before processing emails.
Manually composed emails and their attachments are kept under
`AVERIS_MANUAL_UPLOADS` (default `.cache/manual-uploads`), separate from
`AVERIS_INBOX_SOURCE`.

Open **Gmail Inbox Settings** in the left module bar to connect a dedicated Gmail
account with a Google app password. When automatic reading is enabled, the server
checks the inbox every 60 seconds and adds messages received after enablement to the
work queue as pending cases. The first check establishes a mailbox baseline and does
not import historical mail. Server-sent events refresh the queue when new mail is
stored. Set `AVERIS_GMAIL_POLL=0` to disable polling or
`AVERIS_GMAIL_POLL_INTERVAL` to change the successful-cycle interval.

The inbox loads without inference. Opening a message processes it once and saves
the result; retry runs it again. Review and completed filters include processed
cases. Missing dates, recipients and source evidence are left blank.

For a separate static server:

```bash
python3 -m http.server 4173 --directory frontend
```

This connects to `http://localhost:8000`. Override `window.AVERIS_API_URL` before
`data.js` to use another backend. `data.js` loads API data before rendering each
module; failed requests display an error instead of demo data. The original
examples are archived in `demo-data.js` and are not loaded.

See [the endpoint audit, data contract and setup guide](../docs/frontend-api.md).

## Interface system

The six HTML routes share the original structural styles in `styles.css` and the
product design layer in `interface.css`. The latter owns palette, surface and
radius tokens, typography, responsive layouts, and accessibility fallbacks.
Navigation and controls use glass; message bodies, comparison values and source
text use opaque reading surfaces. The existing local edits to `styles.css` are
preserved.

`motion.js` provides native Web Animations for queue changes and filter feedback;
CSS handles cross-document View Transitions where supported. Browsers without
these features retain normal navigation. Motion stops when reduced motion is
requested; reduced transparency and increased contrast have separate fallbacks.
No runtime packages or external fonts are required. Press Command/Ctrl+K to focus
search, or use the keyboard skip link to reach the content.

Verification: `node --test tests/frontend_api.test.cjs` exercises API hydration,
escaping, all modules, empty states and failures. The redesign was also inspected
in Chrome at 320, 390, 768, 1024 and 1440 pixels using representative API fixtures;
these fixtures are not loaded by the application.
