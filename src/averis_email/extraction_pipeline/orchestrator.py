"""Inspect once, then execute a reusable routing plan with registered handlers."""
from collections.abc import Callable, Mapping
from pathlib import Path

from . import handlers
from .detection import fingerprint, inspect_document
from .models import ExtractionResult, RoutingPlan

Extractor = Callable[[Path, RoutingPlan], dict]


def execute_plan(
    path: str | Path,
    plan: RoutingPlan,
    extractor_registry: Mapping[str, Extractor] | None = None,
) -> ExtractionResult:
    path = Path(path)
    # Keep the original decision immutable; execution may record OCR fallbacks.
    execution = plan.model_copy(deep=True)
    result = ExtractionResult(source=str(path), file_type=execution.file_type,
                              pdf_type=execution.pdf_type, route=execution.route,
                              pages=execution.pages, plan=execution, status="ERROR")
    if execution.validation != "valid":
        result.status = "NEEDS_REVIEW" if execution.validation == "needs_review" else "ERROR"
        result.message = execution.message
        return result
    try:
        if str(path.resolve()) != execution.source or fingerprint(path) != execution.sha256:
            raise ValueError("Document changed or routing plan belongs to another file; inspect again")
        registry = handlers.default_registry() if extractor_registry is None else extractor_registry
        handler = registry.get(execution.route)
        if handler is None:
            raise NotImplementedError(f"No extractor registered for {execution.route}")
        result.extraction = handler(path, execution)
        if any(page.method == "review" for page in execution.pages):
            result.status = "NEEDS_REVIEW"
            result.message = "Some pages produced no usable text after OCR; inspect page reasons."
        else:
            result.status = "EXTRACTED"
    except NotImplementedError as exc:
        result.status = "NOT_IMPLEMENTED"
        result.message = str(exc)
    except Exception as exc:
        result.message = f"Extraction failed: {exc}"
    return result


def extract_file(
    path: str | Path,
    extractor_registry: Mapping[str, Extractor] | None = None,
) -> ExtractionResult:
    return execute_plan(path, inspect_document(path), extractor_registry)
