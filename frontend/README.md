# Shipping Verification UI

The frontend is connected to the FastAPI backend. It includes the inbox, original
message and attachment downloads, seven-field SI/BL comparison, source evidence,
human review, retry and activity history.

From the repository root:

```bash
AVERIS_INBOX_SOURCE='Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2' \
  uvicorn averis_email.web:app --reload --port 8000
```

Open **http://localhost:8000/ui/**. Configure the classifier and extraction
credentials/dependencies as described in the main README before processing emails.

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
