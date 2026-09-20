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

## Classifier selection

Set the pipeline's classifier in `.env`:

```dotenv
EMAIL_CLASSIFIER_MODE=rule_based
```

Available modes are `rule_based` (default), `laya` (local option scoring), and
`llm` (hosted model). For `llm`, `EMAIL_LLM_PROVIDER` selects `nvidia`, `gemini`,
or `huggingface`. The pipeline CLI and web application use this setting;
the standalone Laya/LLM commands still run their named classifier directly.
Process environment values override `.env`. Restart after changing model,
credentials, or threshold settings because backend instances are reused.

`config/classification.py` defines `ClassifierMode` and `CLASSIFIER_MODES`.
To add a strategy, extend the enum and register its factory in
`averis_email/classifier.py`. Invalid modes trigger a classification error and
human review, rather than silently selecting a different mode.

Laya/LLM review outcomes stop the pipeline before attachment processing. The
existing submission contract uses `GENERAL`/`unreadable` as compatibility
placeholders with `NEEDS_REVIEW`; the original null category, detailed review
reason, and scores remain in `diff_detail.classification` on the pipeline result.

## LLM email classification

A separate classifier supports NVIDIA NIM, Gemini, and Hugging Face with one
shared prompt, strict output validation, and human-review outcomes for ambiguity
or failures. Configure the selected provider in `.env` using `.env.example`.

```bash
averis-classify-email email.txt --provider gemini
```

See [LLM classifier setup and API](docs/llm-classifier.md) for models, JSON input,
review routing, and extension points.

## Local Laya classification

Laya ranks the five email intents using option probabilities and routes uncertain
decisions to human review. It runs locally with an optional model dependency:

```bash
pip install -e '.[laya]'
averis-classify-laya email.txt
```

See [Laya setup, scoring, and evaluation](docs/laya-classifier.md).

## PDF extraction

For automatic file routing, use the file extraction pipeline:

```bash
python -m averis_email.extraction_pipeline "path/to/document.pdf"
# Installed command: averis-extract-file "path/to/document.pdf"
```

Python API: `from averis_email.extraction_pipeline import extract_file`.
`extract_file(path)` returns an `ExtractionResult` with detected file type,
PDF type, selected route, status, page diagnostics, and extraction output.

- `.pdf`: inspect every page for extractable text and image content. Text-based
  PDFs (`epdf`) run the existing PDF extractor. Scanned or mixed PDFs go to the
  OCR placeholder and return `NOT_IMPLEMENTED`.
- `.xlsx` and `.txt`: recognized by extension, with explicit `NOT_IMPLEMENTED`
  handlers. Their contents are not parsed yet.
- Blank PDFs return `NEEDS_REVIEW`; missing, unsupported, corrupt, or
  password-protected files return `ERROR`.

Detection is a routing heuristic: a page dominated by an image (at least 50%
of its area) with fewer than 20 text words needs OCR even if it has a text page
number. PDFs with an existing usable OCR text layer may route as `epdf`. Blank
pages do not force OCR. The heuristic does not guarantee text-layer completeness;
thresholds live in `extraction_pipeline/detection.py`.

OCR, XLSX, and TXT extension points are in `extraction_pipeline/handlers.py`.
Mixed PDFs are routed as a whole to OCR to avoid reporting partial extraction
as complete. `EXTRACTED` means the extractor ran, not that every required field
was found; inspect `extraction.missing_focus_fields`. This file-based pipeline is
separate from the email comparison orchestrator.

The existing PDF-only command remains available:

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
