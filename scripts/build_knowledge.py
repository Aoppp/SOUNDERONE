#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.xlsx import write_build_outputs


def main() -> None:
    parser = argparse.ArgumentParser(description="Build SounderOne knowledge from the source workbook")
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("knowledge/sounderone_knowledge.json"))
    parser.add_argument("--report", type=Path, default=Path("knowledge/build_report.json"))
    parser.add_argument(
        "--product-output", type=Path, default=Path("knowledge/product_knowledge.json")
    )
    parser.add_argument(
        "--faq-output", type=Path, default=Path("knowledge/customer_faq.json")
    )
    args = parser.parse_args()
    count, report = write_build_outputs(
        args.source,
        args.output,
        args.report,
        args.product_output,
        args.faq_output,
    )
    summary = report["summary"]
    print(
        f"built {count} documents: {summary['active_documents']} active, "
        f"{summary['review_required_documents']} review-required, "
        f"{summary['handoff_only_documents']} handoff-only, "
        f"{summary['conflicts']} conflicts"
    )


if __name__ == "__main__":
    main()
