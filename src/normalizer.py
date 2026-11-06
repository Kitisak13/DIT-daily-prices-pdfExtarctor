import re
from typing import Optional, Tuple
from src.config import PROVINCE_MAP, THAI_MONTHS


def fix_thai_pdf_text(text: Optional[str]) -> str:
    """Fix Thai font encoding artifacts from DIT PDF export (THSarabunPSK).

    Pre-normalizes compound words containing both sara am and sara aa,
    handles misplaced vowels/tone marks, and restores genuine characters.
    """
    if not text:
        return ""

    text = str(text)

    # 1. Pre-normalization of known multi-vowel/compound words
    pre_map = {
        "อ ำนำจเจริญ": "อำนาจเจริญ",
        "อำนำจเจริญ": "อำนาจเจริญ",
        "ล ำปำง": "ลำปาง",
        "ลำปำง": "ลำปาง",
        "ล ำพูน": "ลำพูน",
        "ลำพูน": "ลำพูน",
        "ก ำแพงเพชร": "กำแพงเพชร",
        "กำแพงเพชร": "กำแพงเพชร",
        "หนองบัวล ำภู": "หนองบัวลำภู",
        "หนองบัวลำภู": "หนองบัวลำภู",
        "สันป่ำตอง": "สันป่าตอง",
        "ข้ำวเหนียวด ำ": "ข้าวเหนียวดำ",
        "ข้าวเหนียวด ำ": "ข้าวเหนียวดำ",
        "ประจ่ำวันที": "ประจำวันที่",
        "ประจำวันที": "ประจำวันที่",
        "ร่ำข้ำว": "รำข้าว",
        "รา้ นค้า": "ร้านค้า",
        "ร้ำนค้ำ": "ร้านค้า",
        "นำ้ ": "น้ำ",
        "น ้ำ": "น้ำ",
        "น้ ำ": "น้ำ",
        "สัปดำห์กอ่ น": "สัปดาห์ก่อน",
        "สัปดำห์ก่อน": "สัปดาห์ก่อน",
        "สัปดำห์นี้": "สัปดาห์นี้",
        "องัคำร": "อังคาร",
        "พธุ": "พุธ",
        "ศกุ ร์": "ศุกร์",
        "ต ่ำ": "ต่ำ",
        "ทั วไป": "ทั่วไป",
    }
    for k, v in pre_map.items():
        text = text.replace(k, v)

    # 2. Fix floating vowels and tone marks
    text = re.sub(r"\)\s*ิ", "ิ)", text)  # e.g. มะล)ิ -> มะลิ)
    text = re.sub(r"([ก-ฮ])\s+ำ", r"\1ำ", text)
    text = re.sub(r"([ก-ฮ])\s+้\s*ำ", r"\1้ำ", text)
    text = re.sub(r"([ก-ฮ])้\s+ำ", r"\1้ำ", text)
    text = re.sub(r"([ก-ฮ])\s+่\s*ำ", r"\1่ำ", text)

    # 3. Protect genuine 'ำ' (sara am) in known words/provinces
    genuine_am_words = [
        "กำแพงเพชร",
        "ลำพูน",
        "ลำปาง",
        "อำนาจเจริญ",
        "หนองบัวลำภู",
        "รำข้าว",
        "ประจำวันที่",
        "น้ำ",
        "สำหรับ",
        "นำเข้า",
        "ข้าวเหนียวดำ",
    ]
    placeholders = {}
    for i, word in enumerate(genuine_am_words):
        ph = f"__AM_{i}__"
        placeholders[ph] = word
        text = text.replace(word, ph)

    # In remaining text, the legacy font used 'ำ' in place of 'า' (sara aa)
    text = text.replace("ำ", "า")

    # Restore protected words
    for ph, word in placeholders.items():
        text = text.replace(ph, word)

    # Clean multiple spaces
    text = re.sub(r"[ \t]+", " ", text).strip()
    return text


def clean_price_cell(val: Optional[str]) -> Tuple[Optional[float], Optional[float]]:
    """Clean and parse a price table cell into (min_price, max_price).

    Treats empty, '-', '—', and blank cells as (None, None).
    Removes commas and extra spaces inside numbers.
    """
    if val is None:
        return None, None

    val = str(val).strip()
    # Check for empty or dash representation
    if not val or val in ["-", "—", "–", "- -", "- - -"] or re.match(r"^[-—–\s]+$", val):
        return None, None

    # Standardize dashes
    val = val.replace("—", "-").replace("–", "-")

    # Case A: range indicated by hyphen
    if "-" in val:
        parts = val.split("-")
        nums = []
        for p in parts:
            p_digits = re.sub(r"[^\d.]", "", p)
            if p_digits:
                try:
                    nums.append(float(p_digits))
                except ValueError:
                    pass
        if len(nums) == 2:
            return nums[0], nums[1]
        elif len(nums) == 1:
            return nums[0], nums[0]
        elif len(nums) > 2:
            return nums[0], nums[-1]

    # Case B: single value or values separated by spaces (e.g. '9,800 9,800' or '9,300')
    tokens = [t for t in re.split(r"\s+", val) if t]
    nums = []
    for t in tokens:
        t_digits = re.sub(r"[^\d.]", "", t)
        if t_digits:
            try:
                nums.append(float(t_digits))
            except ValueError:
                pass

    if len(nums) == 2:
        return nums[0], nums[1]
    elif len(nums) == 1:
        return nums[0], nums[0]
    elif len(nums) > 2:
        return nums[0], nums[-1]

    return None, None


def parse_report_date(
    text: str, filename: Optional[str] = None
) -> Tuple[Optional[str], Optional[int], Optional[int], Optional[int]]:
    """Extract report publication date from report title or filename fallback.

    Handles:
    - Single date: 'ประจำวันที่ 5 พฤศจิกายน 2569' -> ('2026-11-05', 5, 11, 2026)
    - Date range: 'ประจำวันที่ 29 - 30 เมษายน - 1 พฤษภาคม 2567' -> ('2024-05-01', 1, 5, 2024)
    - Filename YYYYMMDD: '20261105160852_7171.pdf' -> ('2026-11-05', 5, 11, 2026)
    - Filename DDMMYY: '010567.pdf' -> ('2024-05-01', 1, 5, 2024)
    """
    if text:
        cleaned = fix_thai_pdf_text(text)
        # Search for: D Month YYYY (all occurrences, pick the last one if range)
        matches = list(re.finditer(r"(\d{1,2})\s+([ก-๙.]+)\s+(\d{4})", cleaned))
        if matches:
            last_m = matches[-1]
            day = int(last_m.group(1))
            month_str = last_m.group(2).strip()
            year = int(last_m.group(3))
            if year > 2400:
                year -= 543
            month = THAI_MONTHS.get(month_str)
            if month:
                return f"{year:04d}-{month:02d}-{day:02d}", day, month, year

        # Secondary text pattern: e.g. YYYY-MM-DD
        m2 = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", cleaned)
        if m2:
            y, m, d = int(m2.group(1)), int(m2.group(2)), int(m2.group(3))
            if y > 2400:
                y -= 543
            return f"{y:04d}-{m:02d}-{d:02d}", d, m, y

    # Fallback to filename
    if filename:
        # Pattern 1: YYYYMMDD... e.g. 20261105160852_7171.pdf
        m_fn1 = re.search(r"(\d{4})(\d{2})(\d{2})", filename)
        if m_fn1:
            y, m, d = int(m_fn1.group(1)), int(m_fn1.group(2)), int(m_fn1.group(3))
            if y > 2400:
                y -= 543
            return f"{y:04d}-{m:02d}-{d:02d}", d, m, y

        # Pattern 2: DDMMYY.pdf e.g. 010567.pdf (Thai Buddhist era 67 -> 2567 -> 2024)
        m_fn2 = re.search(r"^(\d{2})(\d{2})(\d{2})\.pdf$", filename)
        if m_fn2:
            d, m, y_short = int(m_fn2.group(1)), int(m_fn2.group(2)), int(m_fn2.group(3))
            y = (2500 + y_short) - 543
            return f"{y:04d}-{m:02d}-{d:02d}", d, m, y

    return None, None, None, None


def standardize_province(raw_name: Optional[str]) -> Optional[str]:
    """Map Thai province name (e.g. 'จังหวัดพระนครศรีอยุธยา' or 'นครสวรรค์')

    to standardized English province name (e.g. 'Phra Nakhon Si Ayutthaya').
    """
    if not raw_name:
        return None

    cleaned = fix_thai_pdf_text(raw_name)
    cleaned = cleaned.replace("จังหวัด", "").strip()

    # Direct match in dictionary
    if cleaned in PROVINCE_MAP:
        return PROVINCE_MAP[cleaned]

    # Partial match
    for thai_name, eng_name in PROVINCE_MAP.items():
        if thai_name in cleaned or cleaned in thai_name:
            return eng_name

    return None


def validate_record(record: dict) -> Tuple[bool, str]:
    """Validate data quality rules from AGENTS.md and domain sanity boundaries:

    1. report_date must exist.
    2. min_price <= max_price.
    3. section must be valid.
    4. Price sanity checks per product section/unit.
    """
    if not record.get("report_date"):
        return False, "Missing report_date"

    min_p = record.get("min_price")
    max_p = record.get("max_price")

    if min_p is None or max_p is None:
        return False, "Missing price values"

    if min_p > max_p:
        return False, f"Invalid price range: min_price ({min_p}) > max_price ({max_p})"

    section = record.get("section")
    valid_sections = {"PaddyRice", "MilledRice", "OtherRice"}
    if section not in valid_sections:
        return False, f"Invalid section: {section}"

    unit = record.get("unit", "")

    # Domain Sanity Bounds
    if section == "PaddyRice":
        # Paddy rice per ton typically 3,000 - 30,000 THB
        if not (3000 <= min_p <= 30000) or not (3000 <= max_p <= 30000):
            return False, f"PaddyRice price out of realistic range (3000-30000): {min_p} - {max_p}"
    elif section == "MilledRice":
        # Wholesale milled rice per 100kg typically 500 - 6,000 THB
        if not (500 <= min_p <= 6000) or not (500 <= max_p <= 6000):
            return False, f"MilledRice price out of realistic range (500-6000): {min_p} - {max_p}"
    elif section == "OtherRice":
        if "item" in unit:
            # Gunny bags: 5 - 500 THB
            if not (5 <= min_p <= 500) or not (5 <= max_p <= 500):
                return False, f"Gunny bag price out of range (5-500): {min_p} - {max_p}"
        elif "15 kg" in unit:
            # Retail rice 15kg: 150 - 1,500 THB
            if not (150 <= min_p <= 1500) or not (150 <= max_p <= 1500):
                return False, f"Retail rice price out of range (150-1500): {min_p} - {max_p}"
        else:
            # Rice bran, flour, domestic 100kg: 150 - 6,000 THB
            if not (150 <= min_p <= 6000) or not (150 <= max_p <= 6000):
                return False, f"OtherRice price out of range (150-6000): {min_p} - {max_p}"

    return True, "OK"
