"""Word-coordinate PDF extraction; no blocks, spans, OCR, or inferred values."""

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Mapping, Sequence
import unicodedata

import pymupdf

from averis_email.config.keywords import FOCUS_FIELDS, KEYWORD_ALIASES


@dataclass(frozen=True)
class Word:
    x0: float
    y0: float
    x1: float
    y1: float
    text: str

    @property
    def y_center(self) -> float:
        return (self.y0 + self.y1) / 2


def normalize(text: str) -> str:
    return unicodedata.normalize("NFKC", text).casefold().strip().rstrip(":：.")


def lines(words: Sequence[Word]) -> list[list[Word]]:
    """Group words geometrically, ignoring PyMuPDF block/line identifiers."""
    rows: list[list[Word]] = []
    for word in sorted(words, key=lambda w: (w.y_center, w.x0)):
        if rows and abs(word.y_center - rows[-1][0].y_center) <= 2:
            rows[-1].append(word)
        else:
            rows.append([word])
    return [sorted(row, key=lambda w: w.x0) for row in rows]


def extract_page(
    words: Sequence[Word], height: float, page: int = 1,
    aliases: Mapping[str, Sequence[str]] = KEYWORD_ALIASES,
) -> list[dict]:
    """Slide a window of N words by one word for each N-word alias.

    Longest overlapping labels win. Each value ends at the next label's y0;
    the final label ends at the page bottom. Same-row labels therefore can
    produce empty values under the requested strict vertical rule.
    """
    patterns = sorted(
        ((field, alias, tuple(normalize(t) for t in alias.split()))
         for field, variants in aliases.items() for alias in variants),
        key=lambda item: -len(item[2]),
    )
    hits = []
    for row in lines(words):
        occupied: set[int] = set()
        tokens = [normalize(w.text) for w in row]
        for field, alias, pattern in patterns:
            size = len(pattern)
            for start in range(len(row) - size + 1):
                indices = set(range(start, start + size))
                if occupied & indices or tuple(tokens[start:start + size]) != pattern:
                    continue
                matched = row[start:start + size]
                # Do not match a phrase across widely separated table columns.
                if any(b.x0 - a.x1 > 2 * max(a.y1-a.y0, b.y1-b.y0)
                       for a, b in zip(matched, matched[1:])):
                    continue
                occupied.update(indices)
                hits.append({
                    "field": field, "alias": alias, "page": page,
                    "keyword": {
                        "x0": min(w.x0 for w in matched),
                        "y0": min(w.y0 for w in matched),
                        "x1": max(w.x1 for w in matched),
                        "y1": max(w.y1 for w in matched),
                    },
                    "_words": matched,
                })
    hits.sort(key=lambda h: (h["keyword"]["y0"], h["keyword"]["x0"]))
    label_words = {id(w) for hit in hits for w in hit["_words"]}
    for index, hit in enumerate(hits):
        box = hit["keyword"]
        limit = hits[index + 1]["keyword"]["y0"] if index + 1 < len(hits) else height
        selected = [w for w in words if id(w) not in label_words
                    and w.x0 > box["x1"] and box["y0"] < w.y_center < limit
                    and normalize(w.text)]
        hit["value"] = "\n".join(" ".join(w.text for w in row) for row in lines(selected)) or None
        hit["value_words"] = [asdict(w) for row in lines(selected) for w in row]
        hit["next_keyword_y0"] = limit
        del hit["_words"]
    return hits


def extract_pdf(path: str | Path, aliases: Mapping[str, Sequence[str]] = KEYWORD_ALIASES) -> dict:
    """Return all occurrences plus the first nonempty value for each field.

    Values remain verbatim, including numeric units; no unit conversions or
    container-count inference are performed.
    """
    path = Path(path)
    occurrences = []
    empty_pages = []
    page_texts = []
    with pymupdf.open(path, filetype="pdf") as document:
        if not document.is_pdf or document.needs_pass:
            raise ValueError("Expected an unlocked PDF")
        for number, page in enumerate(document, 1):
            words = [Word(*word[:5]) for word in page.get_text("words")]
            page_texts.append("\n".join(" ".join(w.text for w in row) for row in lines(words)))
            if not words:
                empty_pages.append(number)
            occurrences.extend(extract_page(words, page.rect.height, number, aliases))
    return build_extraction_result(path, occurrences, empty_pages, aliases, raw_text="\n\n".join(page_texts))


def build_extraction_result(path, occurrences, empty_pages, aliases=KEYWORD_ALIASES, *, raw_text=""):
    """Normalize native and OCR page results into the same output contract."""
    fields = dict.fromkeys(dict.fromkeys((*FOCUS_FIELDS, *aliases)))
    for hit in occurrences:
        if fields[hit["field"]] is None and hit["value"]:
            fields[hit["field"]] = hit["value"]
    return {"source": str(path), "fields": fields, "occurrences": occurrences,
            "missing_focus_fields": [field for field in FOCUS_FIELDS if fields[field] is None],
            "pages_without_text": empty_pages, "raw_text": raw_text}


def main() -> None:
    parser = ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="+", type=Path, help="PDF files or directories (PDFs only)")
    args = parser.parse_args()
    paths = [pdf for path in args.paths for pdf in (sorted(path.glob("*.pdf")) if path.is_dir() else [path])]
    print(json.dumps([extract_pdf(path) for path in paths], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
