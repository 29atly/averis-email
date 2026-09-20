"""File extraction contracts, independent of the email comparison pipeline."""
from typing import Literal

from pydantic import BaseModel, Field

FileType = Literal["pdf", "xlsx", "txt", "unsupported"]
PdfType = Literal["epdf", "scanned", "mixed", "empty"]


class PdfPage(BaseModel):
    page: int
    kind: Literal["text", "scanned", "blank"]
    word_count: int
    largest_image_fraction: float


class ExtractionResult(BaseModel):
    source: str
    file_type: FileType
    pdf_type: PdfType | None = None
    route: Literal["pdf_extractor", "ocr", "xlsx", "txt"] | None = None
    status: Literal["EXTRACTED", "NOT_IMPLEMENTED", "NEEDS_REVIEW", "ERROR"]
    pages: list[PdfPage] = Field(default_factory=list)
    extraction: dict | None = None
    message: str | None = None
