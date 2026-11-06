import os
from pathlib import Path

# Base Paths
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
PDF_DIR = DATA_DIR / "pdf"
CSV_DIR = DATA_DIR / "extracted" / "csv"
EXCEL_DIR = DATA_DIR / "excel"
LOGS_DIR = DATA_DIR / "logs"

MASTER_CSV_PATH = BASE_DIR / "rice_prices_master.csv"
MASTER_EXCEL_PATH = EXCEL_DIR / "rice_prices_master.xlsx"

# Ensure directories exist
for d in [DATA_DIR, PDF_DIR, CSV_DIR, EXCEL_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)

# DIT API Configuration
DIT_BASE_URL = "https://www.dit.go.th"
DIT_CALENDAR_API = f"{DIT_BASE_URL}/api/FullCalendar/GetsFullCalendar"
DIT_CONTENT_ID = 251531
DIT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
}

# Required Output Schema Columns
OUTPUT_COLUMNS = [
    "report_date",
    "section",
    "category",
    "product_name",
    "province",
    "grade",
    "min_price",
    "max_price",
    "unit",
    "source_file",
    "page_number",
    "extraction_timestamp",
]

# Unique Key Definition for Deduplication
DEDUPLICATION_KEY = [
    "report_date",
    "section",
    "product_name",
    "province",
    "grade",
]

# Thailand Provinces Mapping Dictionary (77 provinces)
PROVINCE_MAP = {
    "กรุงเทพมหานคร": "Bangkok",
    "กระบี่": "Krabi",
    "กาญจนบุรี": "Kanchanaburi",
    "กาฬสินธุ์": "Kalasin",
    "กำแพงเพชร": "Kamphaeng Phet",
    "ขอนแก่น": "Khon Kaen",
    "จันทบุรี": "Chanthaburi",
    "ฉะเชิงเทรา": "Chachoengsao",
    "ชลบุรี": "Chonburi",
    "ชัยนาท": "Chainat",
    "ชัยภูมิ": "Chaiyaphum",
    "ชุมพร": "Chumphon",
    "เชียงราย": "Chiang Rai",
    "เชียงใหม่": "Chiang Mai",
    "ตรัง": "Trang",
    "ตราด": "Trat",
    "ตาก": "Tak",
    "นครนายก": "Nakhon Nayok",
    "นครปฐม": "Nakhon Pathom",
    "นครพนม": "Nakhon Phanom",
    "นครราชสีมา": "Nakhon Ratchasima",
    "นครศรีธรรมราช": "Nakhon Si Thammarat",
    "นครสวรรค์": "Nakhon Sawan",
    "นนทบุรี": "Nonthaburi",
    "นราธิวาส": "Narathiwat",
    "น่าน": "Nan",
    "บึงกาฬ": "Bueng Kan",
    "บุรีรัมย์": "Buriram",
    "ปทุมธานี": "Pathum Thani",
    "ประจวบคีรีขันธ์": "Prachuap Khiri Khan",
    "ปราจีนบุรี": "Prachinburi",
    "ปัตตานี": "Pattani",
    "พระนครศรีอยุธยา": "Phra Nakhon Si Ayutthaya",
    "พังงา": "Phang Nga",
    "พัทลุง": "Phatthalung",
    "พิจิตร": "Phichit",
    "พิษณุโลก": "Phitsanulok",
    "เพชรบุรี": "Phetchaburi",
    "เพชรบูรณ์": "Phetchabun",
    "แพร่": "Phrae",
    "พะเยา": "Phayao",
    "ภูเก็ต": "Phuket",
    "มหาสารคาม": "Maha Sarakham",
    "มุกดาหาร": "Mukdahan",
    "แม่ฮ่องสอน": "Mae Hong Son",
    "ยะลา": "Yala",
    "ยโสธร": "Yasothon",
    "ร้อยเอ็ด": "Roi Et",
    "ระนอง": "Ranong",
    "ระยอง": "Rayong",
    "ราชบุรี": "Ratchaburi",
    "ลพบุรี": "Lopburi",
    "ลำปาง": "Lampang",
    "ลำพูน": "Lamphun",
    "เลย": "Loei",
    "ศรีสะเกษ": "Si Sa Ket",
    "สกลนคร": "Sakon Nakhon",
    "สงขลา": "Songkhla",
    "สตูล": "Satun",
    "สมุทรปราการ": "Samut Prakan",
    "สมุทรสงคราม": "Samut Songkhram",
    "สมุทรสาคร": "Samut Sakhon",
    "สระแก้ว": "Sa Kaeo",
    "สระบุรี": "Saraburi",
    "สิงห์บุรี": "Sing Buri",
    "สุโขทัย": "Sukhothai",
    "สุพรรณบุรี": "Suphan Buri",
    "สุราษฎร์ธานี": "Surat Thani",
    "สุรินทร์": "Surin",
    "หนองคาย": "Nong Khai",
    "หนองบัวลำภู": "Nong Bua Lamphu",
    "อ่างทอง": "Ang Thong",
    "อำนาจเจริญ": "Amnat Charoen",
    "อุดรธานี": "Udon Thani",
    "อุตรดิตถ์": "Uttaradit",
    "อุทัยธานี": "Uthai Thani",
    "อุบลราชธานี": "Ubon Ratchathani",
}

# Thai Months Mapping
THAI_MONTHS = {
    "มกราคม": 1,
    "กุมภาพันธ์": 2,
    "มีนาคม": 3,
    "เมษายน": 4,
    "พฤษภาคม": 5,
    "มิถุนายน": 6,
    "กรกฎาคม": 7,
    "สิงหาคม": 8,
    "กันยายน": 9,
    "ตุลาคม": 10,
    "พฤศจิกายน": 11,
    "ธันวาคม": 12,
    "ม.ค.": 1,
    "ก.พ.": 2,
    "มี.ค.": 3,
    "เม.ย.": 4,
    "พ.ค.": 5,
    "มิ.ย.": 6,
    "ก.ค.": 7,
    "ส.ค.": 8,
    "ก.ย.": 9,
    "ต.ค.": 10,
    "พ.ย.": 11,
    "ธ.ค.": 12,
}

