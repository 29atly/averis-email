# Document routing

`inspect_document(path)` validates contents and returns a serializable `RoutingPlan` without running OCR. `execute_plan(path, plan, extractor_registry=None)` executes that decision. `extract_file(path)` combines both operations.

The plan records the supplied extension, detected format, content fingerprint, validation outcome, detector version, and per-page decisions with reasons. Execution checks the fingerprint and operates on a copy of the plan so fallback decisions do not alter the original inspection result.

## Format policy

PDF signatures are checked before filename hints, then the PDF parser validates the file. ZIP-based Office documents must declare a supported main part through package relationships and content types, then pass the corresponding parser. Macro formats and arbitrary ZIP archives are unsupported. `.docs` is an alias for validated Word OOXML only.

Plain text has no unique signature. Accept `.txt` and extensionless text using UTF-8 or BOM-marked UTF-16/32; reject undecodable input and binary control characters. Arbitrary unknown extensions are not automatically treated as text. Strong binary format evidence overrides filename hints and records a mismatch.

## PDF policy

Each page selects `native`, `ocr`, `blank`, or `review`. Inspection considers native text quality, union image coverage (including tiled or overlapping images), text position relative to large images, drawings, and a low-resolution render for apparent blanks. Native text is used for searchable scans when the text layer passes these checks. OCR uses one whole-page result for ambiguous hybrid pages, avoiding duplicate native/OCR text.

Thresholds are heuristics, not calibrated confidence values. Photographs, complex graphics, sparse searchable scans, and plausible-looking corrupt text can still require review. Region-level OCR is intentionally deferred. A missing business field does not trigger OCR.

The OCR adapter uses the supplied page plan, checks native text quality before mapping fields, performs at most one OCR fallback per page, and marks pages without usable OCR output for review. Missing OCR dependencies are extraction errors, not document-format decisions.

## Extractor integration

Registry handlers follow `(path: Path, plan: RoutingPlan) -> dict`. Supply a mapping to `execute_plan` or `extract_file` to replace the defaults. Keep original source locations in the handler output: page/bounding box for PDFs, sheet/cell for spreadsheets, paragraph/table location for Word documents. An unavailable registered route returns `NOT_IMPLEMENTED`.

## Evaluation

Keep a labeled corpus of native, scanned, mixed, searchable-scan, hybrid, tiled-image, outlined-text, multilingual, renamed, malformed, and encrypted documents. Track routing decisions against page labels, missed content, unnecessary OCR, extraction accuracy, and latency. Tune thresholds on held-out documents rather than optimizing to a few examples.

## Custom handler example

```python
from averis_email.extraction_pipeline import inspect_document, execute_plan
from averis_email.extraction_pipeline.handlers import default_registry

registry = default_registry()
registry["xlsx"] = lambda path, plan: my_spreadsheet_extractor(path)
plan = inspect_document("upload.xlsx")
result = execute_plan("upload.xlsx", plan, registry)
```

An explicitly supplied registry replaces the default mapping; start with
`default_registry()` to override one format. Handlers must accept validated
contents independently of filename extensions (use file streams where needed).
The built-in `structured` module supplies XLSX, DOCX/`.docs`, and TXT
extractors. Its format functions accept one `Path` argument.

The default PaddleOCR engine is English. A custom PDF handler can call
`extract_ocr_pdf(path, page_details=plan.pages, engine=your_engine)` to choose
languages or reuse an engine across requests. Paddle line boxes are split into
approximate word boxes for the existing keyword mapper; they are not exact
character-level geometry. Tests use a fake engine and do not validate real-model
recognition accuracy.

## Email pipeline integration

`stages.ingestion.read_document(loader, attachment_path)` obtains bytes using
`loader.read_bytes`, writes a private temporary file, and invokes `extract_file`.
This supports both local and HTTP-backed Inbox loaders. The temporary file is
removed after extraction, while the original attachment path is retained in the
`ExtractedDoc` returned to the email pipeline.

Adapters return raw text only (`raw_text`, plus `text_by_page` and
`pages_without_text` for PDFs). Ingestion passes that text under `_raw` to the
semantic field extractor in `stages.extraction`, which owns rule/Gemini field
extraction. The standalone file API returns the raw-text result directly. Non-EXTRACTED outcomes and empty
text mark the attachment unreadable, preventing partial OCR from being reported
as a successful comparison.

The structured extractors were recovered individually from the saved working
changes; the Git stash itself was left intact. XLSX uses a stream so renamed
workbooks are accepted after content validation. TXT uses the same UTF decoding
policy as detection, and Word supports OOXML `.docs` aliases.
