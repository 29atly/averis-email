import argparse

from .orchestrator import extract_file
from .detection import inspect_document


def main():
    parser = argparse.ArgumentParser(description="Detect and route a PDF, XLSX, DOCX, or TXT file for extraction.")
    parser.add_argument("file")
    parser.add_argument("--inspect-only", action="store_true", help="Print a routing plan without extraction")
    args = parser.parse_args()
    if args.inspect_only:
        plan = inspect_document(args.file)
        print(plan.model_dump_json(indent=2))
        return 0 if plan.validation == "valid" else 1
    result = extract_file(args.file)
    print(result.model_dump_json(indent=2))
    return 1 if result.status == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
