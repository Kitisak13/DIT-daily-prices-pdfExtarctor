from pathlib import Path
from typing import Dict, List, Tuple
import pandas as pd

from src.config import (
    CSV_DIR,
    DEDUPLICATION_KEY,
    EXCEL_DIR,
    MASTER_CSV_PATH,
    MASTER_EXCEL_PATH,
    OUTPUT_COLUMNS,
)


def save_daily_csv(records: List[Dict], report_date: str) -> Path:
    """Save records for a specific day to /data/extracted/csv/YYYY-MM-DD.csv."""
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    # Ensure all required columns exist in specified order
    for col in OUTPUT_COLUMNS:
        if col not in df.columns:
            df[col] = None
    df = df[OUTPUT_COLUMNS]

    out_file = CSV_DIR / f"{report_date}.csv"
    df.to_csv(out_file, index=False, encoding="utf-8-sig")
    return out_file


def update_master_csv(new_records: List[Dict]) -> Tuple[int, int]:
    """Append new records to rice_prices_master.csv, eliminating duplicates based on

    (report_date, section, product_name, province, grade).
    Returns: (total_master_count, added_count)
    """
    if not new_records:
        if MASTER_CSV_PATH.exists():
            return len(pd.read_csv(MASTER_CSV_PATH)), 0
        return 0, 0

    new_df = pd.DataFrame(new_records)
    for col in OUTPUT_COLUMNS:
        if col not in new_df.columns:
            new_df[col] = None
    new_df = new_df[OUTPUT_COLUMNS]

    if MASTER_CSV_PATH.exists():
        existing_df = pd.read_csv(MASTER_CSV_PATH)
        combined_df = pd.concat([existing_df, new_df], ignore_index=True)
    else:
        combined_df = new_df

    # Deduplicate
    initial_count = len(combined_df)
    deduped_df = combined_df.drop_duplicates(subset=DEDUPLICATION_KEY, keep="last")
    added_count = len(new_records) - (initial_count - len(deduped_df))

    deduped_df.to_csv(MASTER_CSV_PATH, index=False, encoding="utf-8-sig")
    return len(deduped_df), added_count


def export_master_excel() -> Path:
    """Export Master Dataset into an Excel workbook with sheets:

    - PaddyRice
    - MilledRice
    - OtherRice
    """
    EXCEL_DIR.mkdir(parents=True, exist_ok=True)
    if not MASTER_CSV_PATH.exists():
        # Create empty excel with sheets
        with pd.ExcelWriter(MASTER_EXCEL_PATH, engine="openpyxl") as writer:
            empty_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
            empty_df.to_excel(writer, sheet_name="PaddyRice", index=False)
            empty_df.to_excel(writer, sheet_name="MilledRice", index=False)
            empty_df.to_excel(writer, sheet_name="OtherRice", index=False)
        return MASTER_EXCEL_PATH

    master_df = pd.read_csv(MASTER_CSV_PATH)

    with pd.ExcelWriter(MASTER_EXCEL_PATH, engine="openpyxl") as writer:
        for section in ["PaddyRice", "MilledRice", "OtherRice"]:
            sec_df = master_df[master_df["section"] == section]
            if sec_df.empty:
                sec_df = pd.DataFrame(columns=OUTPUT_COLUMNS)
            sec_df.to_excel(writer, sheet_name=section, index=False)

    return MASTER_EXCEL_PATH

