"""Read local or HTTP-backed attachments through the document router."""
from pathlib import Path
from tempfile import TemporaryDirectory

from averis_email.extraction_pipeline import extract_file
from averis_email.schemas import ExtractedDoc


def read_document(loader, attachment_path: str) -> ExtractedDoc:
    """Pass routed text to the existing semantic field-extraction stage.

    The loader owns attachment access. A private temporary file lets the same
    content-based router process local and HTTP inputs, without trusting the
    attachment name as a filesystem path. Review/error outcomes stay unreadable
    so partial OCR cannot silently pass through comparison.
    """
    doc = ExtractedDoc(attachment_path=attachment_path)
    try:
        data = loader.read_bytes(attachment_path)
        suffix = Path(attachment_path.replace("\\", "/")).suffix
        with TemporaryDirectory(prefix="averis-document-") as folder:
            path = Path(folder) / ("attachment" + suffix)
            path.write_bytes(data)
            result = extract_file(path)
        doc.doc_type = result.file_type
        if result.status != "EXTRACTED":
            doc.readable = False
            doc.error = result.message or f"Document extraction returned {result.status}"
            return doc
        text = (result.extraction or {}).get("raw_text", "")
        if not text.strip():
            doc.readable = False
            doc.error = "Document contains no readable text."
            return doc
        doc.fields = {"_raw": text}
    except Exception as exc:
        doc.readable = False
        doc.error = f"Could not read attachment: {exc}"
    return doc
