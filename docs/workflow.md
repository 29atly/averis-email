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
