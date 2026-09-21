"""File extraction and reusable routing contracts."""
from typing import Literal

from pydantic import BaseModel, Field

FileType = Literal["pdf", "xlsx", "txt", "docx", "unsupported"]
PdfType = Literal["epdf", "scanned", "mixed", "empty"]
Route = Literal["pdf_extractor", "ocr", "xlsx", "txt", "docx"]


class PdfPage(BaseModel):
    page: int
    kind: Literal["text", "scanned", "blank"]
    word_count: int
    largest_image_fraction: float
    method: Literal["native", "ocr", "blank", "review"] = "native"
    image_fraction: float = 0
    text_fraction: float = 0
    bad_character_fraction: float = 0
    reasons: list[str] = Field(default_factory=list)


class RoutingPlan(BaseModel):
    source: str
    supplied_extension: str
    file_type: FileType = "unsupported"
    validation: Literal["valid", "invalid", "unsupported", "locked", "needs_review"] = "invalid"
    detector_version: str = "2.0"
    sha256: str | None = None
    extension_mismatch: bool = False
    pdf_type: PdfType | None = None
    route: Route | None = None
    pages: list[PdfPage] = Field(default_factory=list)
    reasons: list[str] = Field(default_factory=list)
    message: str | None = None


class ExtractionResult(BaseModel):
    source: str
    file_type: FileType
    pdf_type: PdfType | None = None
    route: Route | None = None
    status: Literal["EXTRACTED", "NOT_IMPLEMENTED", "NEEDS_REVIEW", "ERROR"]
    pages: list[PdfPage] = Field(default_factory=list)
    plan: RoutingPlan | None = None
    extraction: dict | None = None
    message: str | None = None
