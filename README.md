# Averis Email Document Comparison

Starter repository for an email-driven document comparison workflow.

## Planned workflow

1. Classify the inbox JSON record.
2. Ingest digital documents, with an OCR or vision fallback for scans.
3. Extract and normalize structured fields.
4. Validate required fields and confidence scores.
5. Compare submitted values against the baseline.
6. Format a JSON response for `/submit`.

The implementation is intentionally left blank. The files below are placeholders for the first development pass.

## Layout

```text
src/averis_email/
  stages/
    classification.py
    ingestion.py
    extraction.py
    validation.py
    comparison.py
    formatting.py
docs/
  workflow.md
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```
