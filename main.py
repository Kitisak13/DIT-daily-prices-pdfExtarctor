import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

from src.ai_fallback import extract_with_gemini
from src.config import DATA_DIR, MASTER_CSV_PATH, MASTER_EXCEL_PATH, PDF_DIR
from src.crawler import crawl_date_range
from src.exporter import export_master_excel, save_daily_csv, update_master_csv
from src.parser import parse_pdf


def process_pdf_file(pdf_path: Path, use_ai: bool = False, api_key: str = None) -> list:
    """Parse a single PDF file, fallback to AI if requested or if library produces 0 records."""
    print(f"Processing: {pdf_path.name}...")
    records = []
    if not use_ai:
        try:
            records = parse_pdf(pdf_path)
        except Exception as e:
            print(f"[Parser Error on {pdf_path.name}]: {e}")

    # Fallback to AI if requested or if parsing returned no records
    if not records and (use_ai or api_key):
        print(f"Attempting AI fallback for {pdf_path.name}...")
        records = extract_with_gemini(pdf_path, api_key=api_key)

    if records:
        # Group by report_date to save daily CSV
        report_date = records[0].get("report_date")
        if report_date:
            daily_csv_path = save_daily_csv(records, report_date)
            print(f"  -> Saved daily CSV: {daily_csv_path.name} ({len(records)} records)")

    return records


def main():
    parser = argparse.ArgumentParser(
        description="DIT Rice Market Price Extraction Pipeline"
    )
    parser.add_argument(
        "--date-from",
        type=str,
        help="Start date for crawling (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--date-to",
        type=str,
        help="End date for crawling (YYYY-MM-DD)",
    )
    parser.add_argument(
        "--latest",
        type=int,
        default=None,
        help="Fetch and process latest N days of reports (e.g. --latest 7)",
    )
    parser.add_argument(
        "--process-local",
        action="store_true",
        help="Process all already-downloaded PDFs in data/pdf/ without crawling",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Use Gemini Agentic AI extractor instead of pdfplumber",
    )
    parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="Gemini API Key for AI extractor",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Re-generate Master Excel from Master CSV",
    )

    args = parser.parse_args()

    if args.export_only:
        excel_path = export_master_excel()
        print(f"Master Excel exported successfully to: {excel_path}")
        return

    pdf_files_to_process = []

    if args.process_local:
        pdf_files_to_process = sorted(list(PDF_DIR.rglob("*.pdf")))
        print(f"Found {len(pdf_files_to_process)} local PDF files to process.")
    else:
        # Determine crawl date range
        today = datetime.now().date()
        if args.date_from and args.date_to:
            start_date = args.date_from
            end_date = args.date_to
        elif args.latest:
            start_date = (today - timedelta(days=args.latest)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")
        else:
            # Default: last 7 days
            start_date = (today - timedelta(days=7)).strftime("%Y-%m-%d")
            end_date = today.strftime("%Y-%m-%d")

        print(f"Checking for reports from {start_date} to {end_date}...")
        pdf_files_to_process = crawl_date_range(start_date, end_date)

    if not pdf_files_to_process:
        print("No PDF files to process.")
        return

    all_new_records = []
    for pdf_path in pdf_files_to_process:
        recs = process_pdf_file(pdf_path, use_ai=args.use_ai, api_key=args.api_key)
        all_new_records.extend(recs)

    if all_new_records:
        total_master, added = update_master_csv(all_new_records)
        print(f"\n[Master CSV Updated]")
        print(f"  Total records in Master: {total_master}")
        print(f"  New records added: {added}")

        excel_path = export_master_excel()
        print(f"  Master Excel exported: {excel_path}")
    else:
        print("\nNo records were extracted.")


if __name__ == "__main__":
    main()

