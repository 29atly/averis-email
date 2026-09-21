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
`extract_file(path)` returns an `ExtractionResult` with a validated routing plan,
PDF type, selected route, status, page diagnostics, and extraction output.

- Contents determine PDF, DOCX/OOXML (including `.docs`), and XLSX types; renamed
  documents record an extension mismatch. Plain text accepts UTF-8 or BOM-marked
  UTF-16/32 using a `.txt` or extensionless filename.
- PDF pages with usable embedded text use PyMuPDF. Scanned and ambiguous hybrid
  pages use PaddleOCR. Mixed documents preserve native text on native pages.
- Install OCR with `pip install -e '.[ocr]'`. Models initialize only when needed.
  The default OCR adapter uses English; supply a configured engine through a
  custom handler for other languages.
- XLSX, DOCX/`.docs`, and TXT route to the built-in structured extractors:
  adjacent spreadsheet cells, Word paragraphs/tables, and labeled text lines.
  All adapters return field occurrences and `raw_text`.
- Blank PDFs and pages without usable OCR output return `NEEDS_REVIEW`.
  Missing, unsupported, corrupt, or password-protected files return `ERROR`,
  with the more specific validation outcome in `result.plan`.

Inspect without loading OCR or extracting fields:

```bash
python -m averis_email.extraction_pipeline document.pdf --inspect-only
```

Use `inspect_document(path)` followed by `execute_plan(path, plan)` to separate
inspection from execution. Execution rejects a changed file and preserves the
original plan. Page reasons explain image coverage, sparse text, and fallback
choices. Detection thresholds remain heuristics requiring validation against
your document corpus.

See [routing contracts and custom extractors](docs/document-routing.md).
`EXTRACTED` means the extractor ran, not that every required field was found;
inspect `extraction.missing_focus_fields`. The email comparison pipeline uses
`stages.ingestion.read_document(loader, attachment_path)` to load attachment
bytes through this same router, then passes `raw_text` to its existing semantic
field extractor. Review/error outcomes stop comparison as unreadable documents.

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
