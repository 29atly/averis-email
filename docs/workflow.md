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

## Implemented PDF keyword pipeline

PDF → PyMuPDF `get_text("words")` → geometric rows → keyword windows →
coordinate-bounded values → JSON.

Only word text and x0/y0/x1/y1 coordinates are used. No block or span extraction
or block/line identifiers participate. Words within 2 points of vertical center
are grouped into rows and ordered left to right. For each configured N-word
alias, an N-word window slides one word at a time. Matching ignores case,
normalizes Unicode width, and ignores trailing colons/periods. Longest
overlapping aliases win; large gaps between words reject cross-column matches.

Keywords are processed page by page in y0/x0 order. Their bounding boxes are
the union of matched word boxes. A value word must satisfy both strict rules:

```python
value.x0 > keyword.x1
keyword.y0 < (value.y0 + value.y1) / 2 < next_keyword.y0
```

The final keyword on each page uses the page bottom as its upper boundary.
Matched keyword words are excluded from values. Multiline values retain line
breaks. Every configured keyword, including secondary fields, forms a boundary.
Add document-specific boundary labels to the same config when needed.

These rules intentionally cannot capture values directly below a header when
their x0 is not greater than the header's x1. Consecutive same-row keywords can
produce an empty interval. Unknown labels cannot stop a preceding field, and
label-like words in body text can match. There is no cross-page continuation,
OCR fallback, column inference, or numeric normalization in this stage.
Missing values are null, with missing focus fields and textless pages reported.

The default config includes the supplied aliases plus observed sample variants
such as `To the Order of`, `B/L Number`, `Total Gross Weight`, and
`No. of Containers or Packages`. Edit aliases centrally or pass a custom mapping
to `extract_pdf(path, aliases=...)`.
