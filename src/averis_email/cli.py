#!/usr/bin/env python3
"""
run.py -- build submission.json end-to-end, and optionally self-score it.

Usage:
    python3 -m averis_email.cli path/to/bundle-data
    python3 -m averis_email.cli http://localhost:8080
    python3 -m averis_email.cli path/to/bundle-data --submit http://localhost:8080
"""
import argparse
import json

from averis_email.data_loader import Inbox
from averis_email.orchestrator import run_pipeline
from averis_email.stages.formatting import build_report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source", help="bundle folder OR http://localhost:8080")
    ap.add_argument("--out", default="submission.json")
    ap.add_argument("--report", default="report.txt",
                     help="human-readable report file (set to '' to skip)")
    ap.add_argument("--submit", default=None,
                     help="POST the result to this server URL for self-scoring")
    args = ap.parse_args()

    inbox = Inbox(args.source)
    emails = inbox.emails()
    print(f"{len(emails)} emails loaded from {args.source}")

    submission, results, errors = {}, [], []
    for email in emails:
        try:
            result = run_pipeline(inbox, email)
            submission[email["email_id"]] = result.to_submission_entry()
            results.append(result)
        except Exception as e:
            errors.append((email["email_id"], str(e)))
            submission[email["email_id"]] = {
                "category": "GENERAL", "status": "NEEDS_REVIEW",
                "review_reason": "unreadable", "has_defect": False, "defect_fields": [],
            }

    with open(args.out, "w") as f:
        json.dump(submission, f, indent=2)
    print(f"wrote {args.out}  ({len(submission)} rows, {len(errors)} pipeline errors)")
    for eid, msg in errors[:10]:
        print(f"  ! {eid}: {msg}")

    if args.report:
        with open(args.report, "w") as f:
            f.write(build_report(results))
        print(f"wrote {args.report}")

    if args.submit:
        score = Inbox(args.submit).submit(submission)
        print(json.dumps(score, indent=2))


if __name__ == "__main__":
    main()
