import os
import re
from datetime import datetime, timezone
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


def _get_target_column_bounds(page: fitz.Page, target_wd: int) -> Tuple[float, float]:
    """Dynamically determine the (x_min, x_max) bounding range for the target weekday column

    by scanning header words (จันทร์, อังคาร, พุธ, พฤหัสบดี, ศุกร์) on the page.
    """
    words = page.get_text("words")
    days_found = []
    for w in sorted(words, key=lambda x: (round(x[1] / 5) * 5, x[0])):
        if w[1] > 100:
            continue
        t = fix_thai_pdf_text(w[4])
        for wd_idx, name in enumerate(["จันทร์", "อังคาร", "พุธ", "พฤหัสบดี", "ศุกร์"]):
            if name in t:
                days_found.append((wd_idx, (w[0] + w[2]) / 2.0))

    centers = {}
    for wd_idx, c in days_found:
        if wd_idx not in centers:
            centers[wd_idx] = c

    if not centers or target_wd not in centers:
        idx = min(max(target_wd, 0), 4)
        return WEEKDAY_FALLBACKS[idx]

    c = centers[target_wd]
    if target_wd > 0 and (target_wd - 1) in centers:
        x_min = (centers[target_wd - 1] + c) / 2.0
    else:
        x_min = c - 35.0

    if (target_wd + 1) in centers:
        x_max = (c + centers[target_wd + 1]) / 2.0
    else:
        x_max = c + 35.0

    return x_min, x_max


def _parse_paddy_page(
    page: fitz.Page,
    p_idx: int,
    date_str: str,
    target_wd: int,
    filename: str,
    now_utc: str,
    initial_category: str = "ข้าวเปลือก",
) -> Tuple[List[Dict], str]:
    """Extract Section 1: PaddyRice records from a given page."""
    records = []
    x_min, x_max = _get_target_column_bounds(page, target_wd)
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

        col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

        # Peek next line if price is slightly offset vertically
        if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
            next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
            next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
            next_left = [w[4] for w in next_row if w[0] < 150]
            if next_col and not standardize_province(fix_thai_pdf_text(" ".join(next_left))):
                col_words = next_col
                i += 1

        if not left_text:
            i += 1
            continue

        # Category switch: e.g. ข้าวเปลือกเจ้า นาปรัง ปี 2567, ข้าวเปลือกหอมมะลิ ปี 2569/70
        if "ข้าวเปลือก" in left_text and not left_text.startswith("จังหวัด"):
            current_category = left_text
            i += 1
            continue

        prov = standardize_province(left_text)
        if prov and "ข้าวเปลือก" in current_category:
            raw_price = " ".join(col_words) if col_words else ""
            min_p, max_p = clean_price_cell(raw_price)
            if min_p is not None and max_p is not None:
                rec = {
                    "report_date": date_str,
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
        i += 1

    return records, current_category


def _parse_milled_page(
    page: fitz.Page,
    p_idx: int,
    date_str: str,
    target_wd: int,
    filename: str,
    now_utc: str,
) -> List[Dict]:
    """Extract Section 2: MilledRice records with full product hierarchy."""
    records = []
    x_min, x_max = _get_target_column_bounds(page, target_wd)
    words = page.get_text("words")

    lines = {}
    for w in words:
        if w[1] < 80:
            continue
        y_key = round(w[1] / 3.0) * 3.0
        lines.setdefault(y_key, []).append(w)

    parent_group = None
    current_product = None
    y_keys = sorted(lines.keys())
    i = 0

    while i < len(y_keys):
        y = y_keys[i]
        row_words = sorted(lines[y], key=lambda x: x[0])
        left_words = [w[4] for w in row_words if w[0] < 125]
        left_text = fix_thai_pdf_text(" ".join(left_words)).strip()

        col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

        # Peek next line if price is slightly offset
        if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
            next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
            next_left = [w[4] for w in next_row if w[0] < 125]
            next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
            if next_col and not any(fix_thai_pdf_text(w) in ["ข้าวใหม่", "100%", "5%"] for w in next_left):
                col_words = next_col
                i += 1

        min_p, max_p = clean_price_cell(" ".join(col_words)) if col_words else (None, None)

        if left_text == "ข้าวหอมมะลิ":
            parent_group = "ข้าวหอมมะลิ"
            current_product = None
            i += 1
            continue
        elif left_text.startswith("(ที่ปลูกในภาคเหนือตอนล่าง"):
            parent_group = None
            current_product = "ข้าวหอมมะลิ (ที่ปลูกในภาคเหนือตอนล่างหรือภาคกลาง)"
        elif left_text in ["ข้าวปทุมธานี", "ปลายข้าวปทุมธานี"]:
            parent_group = None
            current_product = left_text
        elif left_text and left_text != "ข้าวใหม่":
            if parent_group and any(left_text.startswith(k) for k in ["100%", "ปลายข้าว"]):
                current_product = f"{parent_group} {left_text}"
            else:
                current_product = left_text

        grade = "ข้าวใหม่" if left_text == "ข้าวใหม่" else None

        if current_product and min_p is not None and max_p is not None:
            rec = {
                "report_date": date_str,
                "section": "MilledRice",
                "category": "ข้าวสารขายส่งทั่วไป",
                "product_name": current_product,
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
    date_str: str,
    target_wd: int,
    filename: str,
    now_utc: str,
) -> List[Dict]:
    """Extract Section 3: OtherRice records, separating wholesale from Table 2 retail."""
    records = []
    x_min, x_max = _get_target_column_bounds(page, target_wd)
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
    current_prod = None

    while i < len(y_keys):
        y = y_keys[i]
        row_words = sorted(lines[y], key=lambda x: x[0])
        left_words = [w[4] for w in row_words if w[0] < 125]
        left_text = fix_thai_pdf_text(" ".join(left_words)).strip()

        col_words = [w[4] for w in row_words if x_min <= (w[0] + w[2]) / 2.0 <= x_max]

        # Peek next line if price is slightly offset
        if not col_words and i + 1 < len(y_keys) and (y_keys[i + 1] - y <= 4.0):
            next_row = sorted(lines[y_keys[i + 1]], key=lambda x: x[0])
            next_left = [w[4] for w in next_row if w[0] < 125]
            next_col = [w[4] for w in next_row if x_min <= (w[0] + w[2]) / 2.0 <= x_max]
            if next_col and not any(fix_thai_pdf_text(w) in ["ข้าวใหม่", "ร้านค้าปลีกทั่วไป", "100%", "5%"] for w in next_left):
                col_words = next_col
                i += 1

        min_p, max_p = clean_price_cell(" ".join(col_words)) if col_words else (None, None)

        # Detect switch to Table 2 (Retail table)
        all_row_text = fix_thai_pdf_text(" ".join([w[4] for w in row_words]))
        if "ราคาขายปลีกข้าวสาร" in all_row_text or "ราคาขายปลีกข้าวสาร" in left_text:
            table_mode = "retail"
            current_cat = "ราคาขายปลีกข้าวสาร (กรุงเทพฯ และปริมณฑล)"
            unit = "THB per 15 kg"
            parent_prod = None
            current_prod = None
            i += 1
            continue

        if table_mode == "wholesale":
            if "รำข้าว" in left_text:
                current_cat = "รำข้าว"
                unit = "THB per 100 kg"
                parent_prod = None
                current_prod = None
                i += 1
                continue
            elif "ข้าวสาร (ข้าวคัดขายบริโภค" in left_text:
                current_cat = "ข้าวสารบรรจุถุงบริโภคในประเทศ"
                unit = "THB per 100 kg"
                parent_prod = None
                current_prod = None
                i += 1
                continue
            elif "แป้งข้าว" in left_text:
                current_cat = "แป้งข้าว"
                unit = "THB per box (10kg)"
                parent_prod = None
                current_prod = None
                i += 1
                continue
            elif "กระสอบป่าน" in left_text:
                current_cat = "กระสอบป่าน"
                unit = "THB per item"
                parent_prod = None
                current_prod = None
                i += 1
                continue

            grade = None
            if current_cat == "รำข้าว":
                if left_text.startswith("-"):
                    current_prod = f"รำข้าว {left_text[1:].strip()}"
            elif current_cat == "ข้าวสารบรรจุถุงบริโภคในประเทศ":
                if left_text in ["ข้าวสารเหนียวสันป่าตอง (เขี้ยวงู)", "ข้าวสารเหนียว"]:
                    parent_prod = left_text
                    i += 1
                    continue
                elif left_text == "ข้าวใหม่":
                    grade = "ข้าวใหม่"
                elif parent_prod:
                    current_prod = f"ข้าวสารบรรจุถุง {parent_prod}"
                    grade = left_text
                else:
                    current_prod = f"ข้าวสารบรรจุถุง {left_text}"
                    parent_prod = None
            elif current_cat == "แป้งข้าว":
                current_prod = f"แป้ง{left_text}" if not left_text.startswith("แป้ง") else left_text
            elif current_cat == "กระสอบป่าน":
                current_prod = f"กระสอบป่าน {left_text}" if not left_text.startswith("กระสอบ") else left_text
        else:
            # Table 2: Retail
            grade = None
            if left_text in [
                "100% (ข้าวหอมมะลิ)",
                "ข้าวสารเจ้า 100%",
                "ข้าวสารเจ้า 5%",
                "ข้าวสารเหนียว (สันป่าตอง/เขี้ยวงู)",
            ]:
                parent_prod = left_text
                current_prod = f"ข้าวสารขายปลีก {parent_prod}"
                if not col_words:
                    i += 1
                    continue
            elif left_text in ["ร้านค้าปลีกทั่วไป", "ข้าวใหม่", "100%", "5%", "10% เมล็ดยาว", "10% เมล็ดสั้นคละ"]:
                grade = left_text
                current_prod = f"ข้าวสารขายปลีก {parent_prod}"

        if current_prod and min_p is not None and max_p is not None:
            rec = {
                "report_date": date_str,
                "section": "OtherRice",
                "category": current_cat,
                "product_name": current_prod,
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


def parse_pdf(pdf_path: str | Path) -> List[Dict]:
    """Parse a DIT Rice Market Price PDF report into normalized records using PyMuPDF coordinate-based extraction.

    Dynamically handles 3-page and 4-page layouts and all historical variations (2024-2026).
    Sections: PaddyRice, MilledRice, OtherRice.
    """
    pdf_path = Path(pdf_path)
    filename = pdf_path.name
    records: List[Dict] = []
    now_utc = datetime.now(timezone.utc).isoformat()

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        print(f"[Error] Failed to open PDF {pdf_path}: {e}")
        return records

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
    target_wd = dt.weekday()

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
                page, p_idx, date_str, target_wd, filename, now_utc, paddy_category
            )
            records.extend(p_recs)
        elif is_milled:
            m_recs = _parse_milled_page(page, p_idx, date_str, target_wd, filename, now_utc)
            records.extend(m_recs)
        elif is_other:
            o_recs = _parse_other_page(page, p_idx, date_str, target_wd, filename, now_utc)
            records.extend(o_recs)

    return records
