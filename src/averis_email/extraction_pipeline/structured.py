"""Extract raw text from structured file formats (TXT, DOCX, XLSX)."""
from pathlib import Path

from .detection import decode_text


def extract_txt(path: Path) -> dict:
    """Extract raw text from TXT file."""
    raw = path.read_bytes()
    text = decode_text(raw)
    return {
        "source": str(path),
        "raw_text": text,
    }


def extract_docx(path: Path) -> dict:
    """Extract raw text from DOCX file."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    def extract_text(container):
        text_parts = []
        for block in container.iter_inner_content():
            if isinstance(block, Paragraph):
                if block.text.strip():
                    text_parts.append(block.text)
            elif isinstance(block, Table):
                for row in block.rows:
                    row_text = []
                    for cell in row.cells:
                        cell_text = "\n".join(extract_text(cell))
                        if cell_text.strip():
                            row_text.append(cell_text)
                    if row_text:
                        text_parts.append("\t".join(row_text))
        return text_parts

    with path.open("rb") as stream:
        document = Document(stream)
        text = "\n".join(extract_text(document))

    return {
        "source": str(path),
        "raw_text": text,
    }


def extract_xlsx(path: Path) -> dict:
    """Extract raw text from XLSX file."""
    from openpyxl import load_workbook

    stream = path.open("rb")
    try:
        workbook = load_workbook(stream, read_only=True, data_only=True)
    except Exception:
        stream.close()
        raise

    rows_text = []
    try:
        for sheet in workbook.worksheets:
            rows_text.append(f"Sheet: {sheet.title}")
            for row in sheet.iter_rows():
                row_values = [str(cell.value) if cell.value is not None else "" for cell in row]
                while row_values and not row_values[-1]:
                    row_values.pop()
                if row_values:
                    rows_text.append("\t".join(row_values))
    finally:
        workbook.close()
        stream.close()

    text = "\n".join(rows_text)
    return {
        "source": str(path),
        "raw_text": text,
    }
