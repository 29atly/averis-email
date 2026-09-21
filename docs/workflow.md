# Workflow

```text
[Inbox JSON Record]
        |
        v
[Stage 1: Email Classification]
        |
        v
[Stage 2: Hybrid Document Ingestion]
        |
        v
[Stage 3: Schema Extraction & Normalization]
        |
        v
[Stage 4: Deterministic Validator]
        |
        v
[Stage 5: JSON Formatter & /submit]
```

## Decisions to make

- Inbox provider and webhook shape
- PDF/DOCX extraction library
- OCR or vision provider
- LLM provider and structured-output schema
- Confidence threshold and human-review destination
- Persistence layer and `/submit` API framework

## Implemented document text extraction

`averis_email.extraction_pipeline` turns any supported attachment into raw text
and nothing more. PDF pages with a usable text layer use PyMuPDF `get_text()`;
scanned or unusable pages are rasterized and read by PaddleOCR, keeping only
lines at or above the confidence threshold. TXT is decoded (UTF-8/16/32), DOCX
paragraphs and table rows are emitted in document order, and XLSX rows are
tab-separated per sheet.

Every adapter returns `{"source", "raw_text"}`; the PDF adapter also returns
`text_by_page` and `pages_without_text`. No labels, aliases, or field values
are interpreted here. `stages.ingestion` passes `raw_text` to
`stages.extraction`, which owns rule and Gemini field extraction, and
`stages.normalizer` owns value cleaning before comparison.
