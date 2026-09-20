# What's new here

This is the "glue" layer only — the shared contract and the code that wires
the 5 stage files together. The stage files themselves
(`classification.py`, `ingestion.py`, `extraction.py`, `validation.py`,
`comparison.py`) are untouched — still empty, exactly as your teammates left
them.

**Important:** because of that, `cli.py` will NOT run successfully yet — it
imports functions from the stage files that don't exist until your
teammates write them. That's expected. Once each teammate adds their
function (see the required names below), it'll start working piece by
piece.

## New/changed files

- `src/averis_email/schemas.py` — **the shared contract.** Read this first,
  everyone codes against it.
- `src/averis_email/orchestrator.py` — calls the 6 stages in order, catches
  errors from any of them, always produces a valid result.
- `src/averis_email/cli.py` — run this to build `submission.json`.
- `src/averis_email/data_loader.py` — copy of the organizers' `loader.py`,
  reads the inbox/attachments either from the local bundle folder or the
  docker server.
- `src/averis_email/stages/*.py` — each now has a working placeholder
  (dumb heuristics / no-ops) plus a docstring describing exactly what to
  replace it with. Function signatures are the contract — keep them
  unchanged when you write the real logic, and everything else keeps working.
- Renamed the stage-4 naming clash: `validation.py` now does completeness
  checking, `comparison.py` does the SI-vs-BL diff — see their docstrings.

## What each stage file needs to add (exact function names + signatures)

`orchestrator.py` calls these — nothing will run until they exist:

| File | Owner | Must define |
|---|---|---|
| `stages/classification.py` | Email Intelligence | `classify_email(email: dict) -> str`, `find_si_bl(email: dict) -> tuple` |
| `stages/ingestion.py` | Document Processing | `read_document(loader, path: str) -> ExtractedDoc` |
| `stages/extraction.py` | Extraction | `extract_fields(doc: ExtractedDoc) -> ExtractedDoc` |
| `stages/validation.py` | Extraction | `missing_fields(si, bl) -> list[str]` |
| `stages/comparison.py` | Extraction | `compare_fields(si, bl) -> tuple[list, dict]` |

All types (`ExtractedDoc`, `FieldValue`, `PipelineResult`, `FIELDS`,
`CATEGORIES`) come from `schemas.py` — `from averis_email.schemas import ...`

Send your team `schemas.py` + this table today so everyone can start writing
their function independently, even before this whole thing runs once
end-to-end.

## How to run it (once teammates have added their functions)

```bash
pip install -e .
python3 -m averis_email.cli /path/to/extracted/bundle --out submission.json

# or, to self-score against the docker server:
python3 -m averis_email.cli /path/to/bundle --submit http://localhost:8080
```

## Priority if time runs short

192 of 520 attachments are plain `.txt` — get `classification.py` +
`extraction.py` (the `.txt` branch in `ingestion.py` already exists) working
for those first. That alone unlocks real scoring on the biggest chunk of
the dataset before anyone touches PDF/DOCX/OCR.
