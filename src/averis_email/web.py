"""
web.py -- small local API so the frontend/demo can call the pipeline live
instead of only reading submission.json.

Run:
    pip install fastapi uvicorn
    uvicorn averis_email.web:app --reload --port 8000

Then from the frontend:
    GET  http://localhost:8000/emails             -> lightweight list for an inbox view
    GET  http://localhost:8000/emails/{email_id}  -> full pipeline result for one email

CORS is left wide open (allow_origins=["*"]) so the frontend can call this
from any port during the hackathon -- fine for a demo, not for production.
"""
from dataclasses import asdict

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from averis_email.data_loader import Inbox
from averis_email.orchestrator import run_pipeline

app = FastAPI(title="Averis Email Pipeline API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Change "data" to wherever you extracted the bundle, or point this at the
# docker server instead: Inbox("http://localhost:8080")
INBOX = Inbox("data")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/emails")
def list_emails():
    """Lightweight list for a sidebar/inbox view -- does not run the pipeline."""
    return [
        {
            "email_id": e["email_id"],
            "from": e.get("from"),
            "subject": e.get("subject"),
            "has_attachments": bool(e.get("attachments")),
        }
        for e in INBOX.emails()
    ]


@app.get("/emails/{email_id}")
def get_email_result(email_id: str):
    """Runs the full pipeline for one email on demand and returns the
    result, including SI/BL field-level detail for the UI to render."""
    email = next((e for e in INBOX.emails() if e["email_id"] == email_id), None)
    if email is None:
        raise HTTPException(status_code=404, detail="email not found")

    result = run_pipeline(INBOX, email)
    return asdict(result)
