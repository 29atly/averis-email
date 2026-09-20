"""Evaluate fixed Laya gates on a seeded sample; labels never enter inference."""
import argparse
from collections import Counter
from contextlib import redirect_stdout
import json
from pathlib import Path
import random
import sys
import time

from .classifier import LayaEmailClassifier
from .cli import read_email
from .config import LayaSettings


def summarize(rows):
    classified = [row for row in rows if not row["result"]["review_required"]]
    scored = [row for row in rows if row["result"]["suggested_category"] is not None]
    return {
        "total": len(rows), "scored": len(scored), "classified": len(classified),
        "reviewed": len(rows) - len(classified),
        "coverage": len(classified) / len(rows) if rows else 0,
        "accepted_accuracy": sum(row["result"]["category"] == row["expected"] for row in classified) / len(classified) if classified else None,
        "top_choice_accuracy_on_scored": sum(row["result"]["suggested_category"] == row["expected"] for row in scored) / len(scored) if scored else None,
        "review_reasons": dict(Counter(row["result"]["review_reason"] for row in rows if row["result"]["review_required"])),
        "label_counts": dict(Counter(row["expected"] for row in rows)),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data", type=Path, help="Directory containing inbox/ and ground_truth.json")
    parser.add_argument("--limit", type=int, default=40, help="Seeded sample size; 0 uses all records")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("limit must be nonnegative")
    settings = LayaSettings.from_env(args.env_file)
    classifier = LayaEmailClassifier(settings)
    paths = sorted((args.data / "inbox").glob("email_*.json"))
    if not paths:
        parser.error("No inbox email files found")
    random.Random(args.seed).shuffle(paths)
    if args.limit:
        paths = paths[:args.limit]
    # Hold labels separately; no label-based sampling, fitting or prompt changes.
    truth = json.loads((args.data / "ground_truth.json").read_text())
    rows = []
    started = time.monotonic()
    for i, path in enumerate(paths, 1):
        with redirect_stdout(sys.stderr):
            result = classifier.classify(read_email(str(path)))
        rows.append({"email_id": path.stem, "expected": truth[path.stem]["category"],
                     "result": result.model_dump()})
        print(f"{i}/{len(paths)} {path.stem}: {result.status}", file=sys.stderr, flush=True)
    report = {"summary": summarize(rows), "seconds": round(time.monotonic() - started, 2),
              "seed": args.seed, "settings": settings.model_dump(mode="json", exclude={"hf_token"}),
              "rows": rows}
    serialized = json.dumps(report, indent=2)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(serialized + "\n")
        print(json.dumps(report["summary"], indent=2))
    else:
        print(serialized)


if __name__ == "__main__":
    main()
