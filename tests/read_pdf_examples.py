"""Print text extracted from a few PDF attachments with PyMuPDF.

Pass one or more attachment filenames on the command line. When no filenames
are supplied, a small set of example files from the dataset is used.
"""

from argparse import ArgumentParser
import json
from pathlib import Path
from typing import TypedDict

import pymupdf


PROJECT_ROOT = Path(__file__).resolve().parents[1]
ATTACHMENTS_DIR = (
    PROJECT_ROOT
    / "Averis Hackathon Instruction"
    / "sdoc-hackathon-docker"
    / "data_v2"
    / "attachments"
)

EXAMPLE_FILES = (
    "email_059_BL.pdf",
    "email_059_SI.pdf",
    "email_160_BL.pdf",
)


class Coordinates(TypedDict):
    x0: float
    y0: float
    x1: float
    y1: float


class ExtractedWord(TypedDict):
    page: int
    text: str
    coordinates: Coordinates
    block_number: int
    line_number: int
    word_number: int


def extract_pdf_text(file_name: str) -> list[ExtractedWord]:
    """Extract words and their coordinates from one PDF in the dataset."""
    pdf_path = ATTACHMENTS_DIR / file_name

    if not pdf_path.is_file():
        raise FileNotFoundError(f"Attachment not found: {pdf_path}")
    if pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a PDF file, got: {file_name}")

    extracted_words: list[ExtractedWord] = []

    with pymupdf.open(pdf_path) as document:
        for page_number, page in enumerate(document, start=1):
            for x0, y0, x1, y1, text, block, line, word in page.get_text("words"):
                extracted_words.append(
                    {
                        "page": page_number,
                        "text": text,
                        "coordinates": {
                            "x0": x0,
                            "y0": y0,
                            "x1": x1,
                            "y1": y1,
                        },
                        "block_number": block,
                        "line_number": line,
                        "word_number": word,
                    }
                )

    return extracted_words


def main() -> None:
    parser = ArgumentParser(
        description="Extract text from PDF files in the Averis attachment dataset."
    )
    parser.add_argument(
        "file_names",
        nargs="*",
        default=EXAMPLE_FILES,
        help="PDF attachment filename(s); defaults to three sample PDFs",
    )
    args = parser.parse_args()

    for file_name in args.file_names:
        print(f"\n{'=' * 80}\nFile: {file_name}\n{'=' * 80}")
        words = extract_pdf_text(file_name)
        print(
            json.dumps(words, indent=2)
            if words
            else "[No embedded text found; this PDF may require OCR.]"
        )


if __name__ == "__main__":
    main()
