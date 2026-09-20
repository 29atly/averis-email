import argparse

from .orchestrator import extract_file


def main():
    parser = argparse.ArgumentParser(description="Detect and route a PDF, XLSX, or TXT file for extraction.")
    parser.add_argument("file")
    args = parser.parse_args()
    result = extract_file(args.file)
    print(result.model_dump_json(indent=2))
    return 1 if result.status == "ERROR" else 0


if __name__ == "__main__":
    raise SystemExit(main())
