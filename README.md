# Averis Email Document Comparison

Starter repository for an email-driven document comparison workflow.

## Planned workflow

1. Classify the inbox JSON record.
2. Ingest digital documents, with an OCR or vision fallback for scans.
3. Extract and normalize structured fields.
4. Validate required fields and confidence scores.
5. Compare submitted values against the baseline.
6. Format a JSON response for `/submit`.

The PDF keyword extraction stage is implemented. Other workflow stages remain placeholders.

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

## PDF extraction

```bash
python -m averis_email.stages.extraction "path/to/document.pdf"
# Or process only *.pdf files in a directory:
averis-extract-pdf "Averis Hackathon Instruction/sdoc-hackathon-docker/data_v2/attachments" > outputs/extracted.json
```

Python API: `from averis_email.stages.extraction import extract_pdf` and
`result = extract_pdf("document.pdf")`.

Edit `src/averis_email/config/keywords.py` to add aliases. The seven focus fields
are shipper, consignee, notify party, loading/discharge ports, container count,
and gross weight in kilograms. Additional configured fields are also returned.
Output includes raw `fields`, ordered `occurrences` with keyword/value word
coordinates, `missing_focus_fields`, and `pages_without_text`.

Values are verbatim strings, including units and container descriptions; the
extractor does not convert weights, infer counts, or verify that an unqualified
gross-weight label uses kilograms. Inspect occurrences when fields repeat;
`fields` selects the first nonempty occurrence.

```bash
PYTHONPATH=src python -m unittest discover -s tests -p 'test_*.py'
```
