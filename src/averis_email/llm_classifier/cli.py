"""Classify a text file, inbox JSON record, or stdin; emit one JSON result."""
import argparse
import json
import sys
from pathlib import Path

from .classifier import EmailClassifier


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", help="UTF-8 text file, inbox .json file, or - for stdin")
    parser.add_argument("--provider", choices=["nvidia", "gemini", "huggingface"])
    parser.add_argument("--env-file", default=".env")
    args = parser.parse_args()
    try:
        text = sys.stdin.read() if args.source == "-" else Path(args.source).read_text(encoding="utf-8")
        if args.source.lower().endswith(".json"):
            record = json.loads(text)
            if not isinstance(record, dict):
                raise ValueError("Expected one inbox JSON object")
            subject, body = record.get("subject") or "", record.get("body") or ""
            if not isinstance(subject, str) or not isinstance(body, str):
                raise ValueError("Subject and body must be strings")
            text = f"Subject: {subject}\n\n{body}" if subject.strip() or body.strip() else ""
        classifier = EmailClassifier.from_env(args.provider, args.env_file)
    except (OSError, ValueError):
        parser.exit(2, "Cannot load input or configuration. Check the file and provider key/model settings.\n")
    result = classifier.classify(text)
    print(result.model_dump_json(indent=2))
    return 0
