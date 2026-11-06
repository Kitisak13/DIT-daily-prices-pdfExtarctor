import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sys

import fitz

from src.ai_fallback import extract_with_gemini
from src.config import DATA_DIR, MASTER_CSV_PATH, MASTER_EXCEL_PATH, PDF_DIR
from src.crawler import crawl_date_range
from src.exporter import export_master_excel, save_daily_csv, update_master_csv
from src.normalizer import parse_report_date
from src.parser import parse_pdf


def get_pdf_report_date(pdf_path: Path) -> str:
    """Extract report_date from filename or PDF header for chronological sorting."""
    # 1. Fast check from filename without opening the file
    date_str, _, _, _ = parse_report_date("", pdf_path.name)
    if date_str:
        return date_str

    # 2. Fallback to reading first page header with PyMuPDF
    try:
        with fitz.open(pdf_path) as doc:
            p0_text = doc[0].get_text() if len(doc) > 0 else ""
            date_str, _, _, _ = parse_report_date(p0_text, pdf_path.name)
            if date_str:
                return date_str
    except Exception:
        pass
    return pdf_path.name


def process_pdf_file(
    pdf_path: Path,
    multi_column: bool = True,
    use_ai: bool = False,
    api_key: str = None,
) -> list:
    """Parse a single PDF file, fallback to AI if requested or if library produces 0 records."""
    mode_str = "Multi-Column Weekly Matrix" if multi_column else "Single-Day"
    print(f"Processing: {pdf_path.name} ({mode_str})...")
    records = []
    if not use_ai:
        try:
            records = parse_pdf(pdf_path, multi_column=multi_column)
        except Exception as e:
            print(f"[Parser Error on {pdf_path.name}]: {e}")

    # Fallback to AI if requested or if parsing returned no records
    if not records and (use_ai or api_key):
        print(f"Attempting AI fallback for {pdf_path.name}...")
        records = extract_with_gemini(pdf_path, api_key=api_key)

    if records:
        saved_csvs = save_daily_csv(records)
        dates_saved = [f.name for f in saved_csvs]
        print(f"  -> Saved {len(saved_csvs)} daily CSV(s): {', '.join(dates_saved)} (total {len(records)} records)")

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
        "--weekly-only",
        action="store_true",
        help="Download only the last published report of each week (ideal for historical backfills)",
    )
    parser.add_argument(
        "--single-day",
        action="store_true",
        help="Extract only the single day of report header instead of full multi-column week",
    )
    parser.add_argument(
        "--use-ai",
        action="store_true",
        help="Use Gemini Agentic AI extractor instead of PyMuPDF parser",
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
        pdf_files = list(PDF_DIR.rglob("*.pdf"))
        # Sort chronologically by actual report date
        pdf_files_to_process = sorted(pdf_files, key=get_pdf_report_date)
        print(f"Found {len(pdf_files_to_process)} local PDF files to process (sorted chronologically).")
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

        print(f"Checking for reports from {start_date} to {end_date} (weekly_only={args.weekly_only})...")
        pdf_files_to_process = crawl_date_range(start_date, end_date, weekly_only=args.weekly_only)
        pdf_files_to_process = sorted(pdf_files_to_process, key=get_pdf_report_date)

    if not pdf_files_to_process:
        print("No PDF files to process.")
        return

    all_new_records = []
    multi_column = not args.single_day

    for pdf_path in pdf_files_to_process:
        recs = process_pdf_file(
            pdf_path,
            multi_column=multi_column,
            use_ai=args.use_ai,
            api_key=args.api_key,
        )
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
