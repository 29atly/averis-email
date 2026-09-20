"""Run local Laya on a text file, inbox JSON, or stdin."""
import argparse
from contextlib import redirect_stdout
import json
from pathlib import Path
import sys

from .classifier import LayaEmailClassifier
from .config import LayaSettings


def read_email(source):
    text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
    if source.lower().endswith(".json"):
        record = json.loads(text)
        if not isinstance(record, dict):
            raise ValueError("Expected one inbox object")
        subject, body = record.get("subject") or "", record.get("body") or ""
        if not isinstance(subject, str) or not isinstance(body, str):
            raise ValueError("Subject and body must be strings")
        text = f"Subject: {subject}\n\n{body}" if subject.strip() or body.strip() else ""
    return text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--checkpoint", choices=["auto", "english", "multilingual"])
    parser.add_argument("--device", choices=["cpu", "mps", "cuda"])
    args = parser.parse_args()
    try:
        text = read_email(args.source)
        settings = LayaSettings.from_env(args.env_file)
        updates = {name: getattr(args, name) for name in ("checkpoint", "device") if getattr(args, name)}
        settings = LayaSettings.model_validate({**settings.model_dump(), **updates})
    except (ValueError, OSError):
        parser.exit(2, "Invalid email input or Laya configuration.\n")
    # SDK device warnings must not corrupt JSON stdout.
    with redirect_stdout(sys.stderr):
        result = LayaEmailClassifier(settings).classify(text)
    print(result.model_dump_json(indent=2))
    return 0
