import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz

from src.config import OUTPUT_COLUMNS
from src.normalizer import (
    clean_price_cell,
    fix_thai_pdf_text,
    parse_report_date,
    standardize_province,
    validate_record,
)

# Standard Fallback Weekday Bounds (x_min, x_max)
WEEKDAY_FALLBACKS = [
    (165.0, 235.0),  # 0: Mon
    (235.0, 305.0),  # 1: Tue
    (305.0, 375.0),  # 2: Wed
    (375.0, 445.0),  # 3: Thu
    (445.0, 515.0),  # 4: Fri
]


def _get_page_columns(page: fitz.Page) -> Dict[int, Tuple[float, float]]:
    """Dynamically determine the (x_min, x_max) bounding range for each weekday column (0..4)

    by scanning header words (จันทร์, อังคาร, พุธ, พฤหัสบดี, ศุกร์) and 'สัปดาห์นี้' on the page.
    """
    words = page.get_text("words")
    days_found = []
    this_week_center = None

    for w in sorted(words, key=lambda x: (round(x[1] / 5) * 5, x[0])):
        if w[1] > 100:
            continue
        t = fix_thai_pdf_text(w[4])
        for wd_idx, name in enumerate(["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]):
            if name in t:
                days_found.append((wd_idx, (w[0] + w[2]) / 2.0))
        if "สัปดาห์นี้" in t:
            this_week_center = (w[0] + w[2]) / 2.0

    centers = {}
    for wd_idx, c in days_found:
        if wd_idx not in centers:
            centers[wd_idx] = c

    if not centers:
        return {wd: WEEKDAY_FALLBACKS[wd] for wd in range(5)}

    col_bounds = {}
    sorted_wds = sorted(centers.keys())
    for idx, wd in enumerate(sorted_wds):
        c = centers[wd]
        if idx > 0:
            x_min = (centers[sorted_wds[idx - 1]] + c) / 2.0
        else:
            x_min = c - 35.0

        if idx < len(sorted_wds) - 1:
            x_max = (c + centers[sorted_wds[idx + 1]]) / 2.0
        else:
            # Right edge of last weekday (Friday): use "สัปดาห์นี้" column boundary if present
            if this_week_center and this_week_center > c:
                x_max = (c + this_week_center) / 2.0
            else:
                x_max = c + 35.0

        col_bounds[wd] = (x_min, x_max)

    return col_bounds


def _parse_paddy_page(
    page: fitz.Page,
    p_idx: int,
    week_dates: Dict[int, str],
    target_wds: List[int],
    filename: str,
    now_utc: str,
    initial_category: str = "ข้าวเปลือก",
) -> Tuple[List[Dict], str]:
    """Extract Section 1: PaddyRice records from a given page across target weekdays."""
    records = []
    col_bounds = _get_page_columns(page)
    words = page.get_text("words")

    lines = {}
    for w in words:
        if w[1] < 25:
            continue
        y_key = round(w[1] / 3.0) * 3.0
        lines.setdefault(y_key, []).append(w)

    current_category = initial_category
    y_keys = sorted(lines.keys())
    i = 0

    while i < len(y_keys):
        y = y_keys[i]
        row_words = sorted(lines[y], key=lambda x: x[0])
        left_words = [w[4] for w in row_words if w[0] < 150]
        left_text = fix_thai_pdf_text(" ".join(left_words)).strip()

        if not left_text:
            i += 1
            continue

        # Category switch: capture full untruncated name up to x < 350
        if "ข้าวเปลือก" in left_text and not left_text.startswith("จังหวัด"):
            full_header_words = [
                w[4]
                for w in row_words
                if w[0] < 350 and "บาท/ตัน" not in fix_thai_pdf_text(w[4])
            ]
            current_category = fix_thai_pdf_text(" ".join(full_header_words)).strip()
            i += 1
            continue

        prov = standardize_province(left_text)
        if prov and "ข้าวเปลือก" in current_category:
            for wd in target_wds:
                if wd not in col_bounds:
                    continue
                x_min, x_max = col_bounds[wd]
                col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

                # Peek next line if price is slightly offset vertically
                if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
                    next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
                    next_left = [w[4] for w in next_row if w[0] < 150]
                    if not standardize_province(fix_thai_pdf_text(" ".join(next_left))):
                        next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
                        if next_col:
                            col_words = next_col

                raw_price = " ".join(col_words) if col_words else ""
                min_p, max_p = clean_price_cell(raw_price)
                if min_p is not None and max_p is not None:
                    rec = {
                        "report_date": week_dates[wd],
                        "section": "PaddyRice",
                        "category": current_category,
                        "product_name": current_category,
                        "province": prov,
                        "grade": None,
                        "min_price": min_p,
                        "max_price": max_p,
                        "unit": "THB per ton",
                        "source_file": filename,
                        "page_number": p_idx + 1,
                        "extraction_timestamp": now_utc,
                    }
                    ok, _ = validate_record(rec)
                    if ok:
                        records.append(rec)
        elif left_text.startswith("จังหวัด"):
            print(f"[Warning] Unrecognized province in {filename} (p.{p_idx + 1}): {left_text}")

        i += 1

    return records, current_category


def _parse_milled_page(
    page: fitz.Page,
    p_idx: int,
    week_dates: Dict[int, str],
    target_wds: List[int],
    filename: str,
    now_utc: str,
) -> List[Dict]:
    """Extract Section 2: MilledRice records with full product hierarchy across target weekdays."""
    records = []
    col_bounds = _get_page_columns(page)
    words = page.get_text("words")

    lines = {}
    for w in words:
        if w[1] < 80:
            continue
        y_key = round(w[1] / 3.0) * 3.0
        lines.setdefault(y_key, []).append(w)

    parent_group = None
    last_product = None
    y_keys = sorted(lines.keys())
    i = 0

    while i < len(y_keys):
        y = y_keys[i]
        row_words = sorted(lines[y], key=lambda x: x[0])
        left_words = [w[4] for w in row_words if w[0] < 125]
        left_text = fix_thai_pdf_text(" ".join(left_words)).strip()

        if not left_text:
            i += 1
            continue

        row_product = None
        grade = None

        if left_text == "ข้าวหอมมะลิ":
            parent_group = "ข้าวหอมมะลิ"
            last_product = None
            i += 1
            continue
        elif left_text.startswith("(ที่ปลูกในภาคเหนือตอนล่าง"):
            parent_group = None
            row_product = "ข้าวหอมมะลิ (ที่ปลูกในภาคเหนือตอนล่างหรือภาคกลาง)"
            last_product = row_product
        elif left_text in ["ข้าวปทุมธานี", "ปลายข้าวปทุมธานี"]:
            parent_group = None
            row_product = left_text
            last_product = row_product
        elif left_text == "ข้าวใหม่":
            grade = "ข้าวใหม่"
            row_product = last_product
        elif left_text:
            if parent_group and left_text.startswith("100%"):
                row_product = f"{parent_group} {left_text}"
            else:
                row_product = left_text
            last_product = row_product

        if not row_product:
            i += 1
            continue

        for wd in target_wds:
            if wd not in col_bounds:
                continue
            x_min, x_max = col_bounds[wd]
            col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

            # Backward peek: check previous line if it had price but no product name
            if not col_words and i > 0 and (y - y_keys[i - 1] <= 4.0):
                prev_row = sorted(lines[y_keys[i - 1]], key=lambda x: x[0])
                prev_left = [w[4] for w in prev_row if w[0] < 125]
                if not prev_left:
                    prev_col = [w[4] for w in prev_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
                    if prev_col:
                        col_words = prev_col

            # Forward peek: check next line if price is slightly lower
            if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
                next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
                next_left = [w[4] for w in next_row if w[0] < 125]
                if not next_left or not any(fix_thai_pdf_text(w) in ["ข้าวใหม่", "100%", "5%"] for w in next_left):
                    next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
                    if next_col:
                        col_words = next_col

            min_p, max_p = clean_price_cell(" ".join(col_words)) if col_words else (None, None)
            if min_p is not None and max_p is not None:
                rec = {
                    "report_date": week_dates[wd],
                    "section": "MilledRice",
                    "category": "ข้าวสารขายส่งทั่วไป",
                    "product_name": row_product,
                    "province": None,
                    "grade": grade,
                    "min_price": min_p,
                    "max_price": max_p,
                    "unit": "THB per 100 kg",
                    "source_file": filename,
                    "page_number": p_idx + 1,
                    "extraction_timestamp": now_utc,
                }
                ok, _ = validate_record(rec)
                if ok:
                    records.append(rec)
        i += 1

    return records


def _parse_other_page(
    page: fitz.Page,
    p_idx: int,
    week_dates: Dict[int, str],
    target_wds: List[int],
    filename: str,
    now_utc: str,
) -> List[Dict]:
    """Extract Section 3: OtherRice records, separating wholesale from Table 2 retail across target weekdays."""
    records = []
    col_bounds = _get_page_columns(page)
    words = page.get_text("words")

    lines = {}
    for w in words:
        if w[1] < 70:
            continue
        y_key = round(w[1] / 3.0) * 3.0
        lines.setdefault(y_key, []).append(w)

    y_keys = sorted(lines.keys())
    i = 0
    table_mode = "wholesale"
    current_cat = "รำข้าว"
    unit = "THB per 100 kg"
    parent_prod = None
    last_product = None

    while i < len(y_keys):
        y = y_keys[i]
        row_words = sorted(lines[y], key=lambda x: x[0])
        left_words = [w[4] for w in row_words if w[0] < 125]
        left_text = fix_thai_pdf_text(" ".join(left_words)).strip()

        # Detect switch to Table 2 (Retail table)
        all_row_text = fix_thai_pdf_text(" ".join([w[4] for w in row_words]))
        if "ราคาขายปลีกข้าวสาร" in all_row_text or "ราคาขายปลีกข้าวสาร" in left_text:
            table_mode = "retail"
            current_cat = "ราคาขายปลีกข้าวสาร (กรุงเทพฯ และปริมณฑล)"
            unit = "THB per 15 kg"
            parent_prod = None
            last_product = None
            i += 1
            continue

        if not left_text:
            i += 1
            continue

        row_product = None
        grade = None

        if table_mode == "wholesale":
            if "รำข้าว" in left_text:
                current_cat = "รำข้าว"
                unit = "THB per 100 kg"
                parent_prod = None
                last_product = None
                i += 1
                continue
            elif "ข้าวสาร (ข้าวคัดขายบริโภค" in left_text:
                current_cat = "ข้าวสารบรรจุถุงบริโภคในประเทศ"
                unit = "THB per 100 kg"
                parent_prod = None
                last_product = None
                i += 1
                continue
            elif "แป้งข้าว" in left_text:
                current_cat = "แป้งข้าว"
                unit = "THB per box (10kg)"
                parent_prod = None
                last_product = None
                i += 1
                continue
            elif "กระสอบป่าน" in left_text:
                current_cat = "กระสอบป่าน"
                unit = "THB per item"
                parent_prod = None
                last_product = None
                i += 1
                continue

            if current_cat == "รำข้าว":
                if left_text.startswith("-"):
                    row_product = f"รำข้าว {left_text[1:].strip()}"
                    last_product = row_product
            elif current_cat == "ข้าวสารบรรจุถุงบริโภคในประเทศ":
                if left_text in ["ข้าวสารเหนียวสันป่าตอง (เขี้ยวงู)", "ข้าวสารเหนียว"]:
                    parent_prod = left_text
                    last_product = None
                    i += 1
                    continue
                elif left_text == "ข้าวใหม่":
                    grade = "ข้าวใหม่"
                    row_product = last_product
                elif parent_prod:
                    row_product = f"ข้าวสารบรรจุถุง {parent_prod}"
                    grade = left_text
                    last_product = row_product
                else:
                    row_product = f"ข้าวสารบรรจุถุง {left_text}"
                    grade = None
                    last_product = row_product
                    parent_prod = None
            elif current_cat == "แป้งข้าว":
                row_product = f"แป้ง{left_text}" if not left_text.startswith("แป้ง") else left_text
                last_product = row_product
            elif current_cat == "กระสอบป่าน":
                row_product = f"กระสอบป่าน {left_text}" if not left_text.startswith("กระสอบ") else left_text
                last_product = row_product
        else:
            # Table 2: Retail
            if left_text in [
                "100% (ข้าวหอมมะลิ)",
                "ข้าวสารเจ้า 100%",
                "ข้าวสารเจ้า 5%",
                "ข้าวสารเหนียว (สันป่าตอง/เขี้ยวงู)",
            ]:
                parent_prod = left_text
                row_product = f"ข้าวสารขายปลีก {parent_prod}"
                last_product = row_product
            elif left_text in ["ร้านค้าปลีกทั่วไป", "ข้าวใหม่", "100%", "5%", "10% เมล็ดยาว", "10% เมล็ดสั้นคละ"]:
                grade = left_text
                row_product = f"ข้าวสารขายปลีก {parent_prod}" if parent_prod else last_product

        if not row_product:
            i += 1
            continue

        for wd in target_wds:
            if wd not in col_bounds:
                continue
            x_min, x_max = col_bounds[wd]
            col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

            # Backward peek
            if not col_words and i > 0 and (y - y_keys[i - 1] <= 4.0):
                prev_row = sorted(lines[y_keys[i - 1]], key=lambda x: x[0])
                prev_left = [w[4] for w in prev_row if w[0] < 125]
                if not prev_left:
                    prev_col = [w[4] for w in prev_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
                    if prev_col:
                        col_words = prev_col

            # Forward peek
            if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
                next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
                next_left = [w[4] for w in next_row if w[0] < 125]
                if not next_left or not any(fix_thai_pdf_text(w) in ["ข้าวใหม่", "ร้านค้าปลีกทั่วไป", "100%", "5%"] for w in next_left):
                    next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
                    if next_col:
                        col_words = next_col

            min_p, max_p = clean_price_cell(" ".join(col_words)) if col_words else (None, None)
            if min_p is not None and max_p is not None:
                rec = {
                    "report_date": week_dates[wd],
                    "section": "OtherRice",
                    "category": current_cat,
                    "product_name": row_product,
                    "province": None,
                    "grade": grade,
                    "min_price": min_p,
                    "max_price": max_p,
                    "unit": unit,
                    "source_file": filename,
                    "page_number": p_idx + 1,
                    "extraction_timestamp": now_utc,
                }
                ok, _ = validate_record(rec)
                if ok:
                    records.append(rec)
        i += 1

    return records


def parse_pdf(pdf_path: str | Path, multi_column: bool = True) -> List[Dict]:
    """Parse a DIT Rice Market Price PDF report into normalized records using PyMuPDF coordinate-based extraction.

    Args:
        pdf_path: Path to the PDF file.
        multi_column: If True (default), extracts all active weekdays (Monday-Friday up to report_wd)
                      in the table matrix, capturing price adjustments and maximizing data coverage.
                      If False, extracts only the single weekday corresponding to the report header date.
    """
    pdf_path = Path(pdf_path)
    filename = pdf_path.name
    records: List[Dict] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    try:
        with fitz.open(pdf_path) as doc:
            total_pages = len(doc)
            if total_pages == 0:
                return records

            # 1. Extract Report Date from first page or filename
            p1_text = doc[0].get_text() or ""
            date_str, day, month, year = parse_report_date(p1_text, filename)

            if not date_str:
                print(f"[Warning] Could not extract report_date from {filename}")
                return records

            dt = datetime.strptime(date_str, "%Y-%m-%d")
            report_wd = dt.weekday()
            monday_dt = dt - timedelta(days=report_wd)
            week_dates = {wd: (monday_dt + timedelta(days=wd)).strftime("%Y-%m-%d") for wd in range(5)}

            # Never extract columns in the future relative to this report date
            max_allowed_wd = min(report_wd, 4)
            target_wds = list(range(max_allowed_wd + 1)) if multi_column else [max_allowed_wd]

            # 2. Iterate through pages and classify section
            paddy_category = "ข้าวเปลือก"
            for p_idx in range(total_pages):
                page = doc[p_idx]
                page_text = fix_thai_pdf_text(page.get_text())

                is_paddy = "ข้าวเปลือก" in page_text and not ("ขายส่งทั่วไป" in page_text or "รำข้าว" in page_text)
                is_milled = ("ขายส่งทั่วไป" in page_text or "มาตรฐานกระทรวงพาณิชย์" in page_text) and "รำข้าว" not in page_text
                is_other = "รำข้าว" in page_text or "ขายปลีก" in page_text or "กระสอบป่าน" in page_text

                if is_paddy:
                    p_recs, paddy_category = _parse_paddy_page(
                        page, p_idx, week_dates, target_wds, filename, now_utc, paddy_category
                    )
                    records.extend(p_recs)
                elif is_milled:
                    m_recs = _parse_milled_page(page, p_idx, week_dates, target_wds, filename, now_utc)
                    records.extend(m_recs)
                elif is_other:
                    o_recs = _parse_other_page(page, p_idx, week_dates, target_wds, filename, now_utc)
                    records.extend(o_recs)
    except Exception as e:
        print(f"[Error] Failed to open/parse PDF {pdf_path}: {e}")
        return records

    return records
