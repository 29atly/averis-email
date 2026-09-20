"""File -> format detection -> PDF inspection -> selected extraction handler."""
from pathlib import Path

from . import handlers
from .detection import inspect_pdf, recognize_file_type
from .models import ExtractionResult


def extract_file(path: str | Path) -> ExtractionResult:
    path = Path(path)
    result = ExtractionResult(source=str(path), file_type=recognize_file_type(path), status="ERROR")
    if not path.is_file():
        result.message = "Input must be an existing file."
        return result
    if result.file_type == "unsupported":
        result.message = "Unsupported file type. Expected .pdf, .xlsx, or .txt."
        return result
    try:
        if result.file_type == "pdf":
            result.pdf_type, result.pages = inspect_pdf(path)
            if result.pdf_type == "empty":
                result.status = "NEEDS_REVIEW"
                result.message = "PDF contains no detected text or visible page content."
                return result
            result.route = "pdf_extractor" if result.pdf_type == "epdf" else "ocr"
        else:
            result.route = result.file_type
        handler = {"pdf_extractor": handlers.extract_epdf, "ocr": handlers.extract_with_ocr,
                   "xlsx": handlers.extract_xlsx, "txt": handlers.extract_txt}[result.route]
        result.extraction = handler(path)
        result.status = "EXTRACTED"
    except NotImplementedError as exc:
        result.status = "NOT_IMPLEMENTED"
        result.message = str(exc)
    except Exception as exc:
        result.status = "ERROR"
        result.message = f"File inspection or extraction failed: {exc}"
    return result
