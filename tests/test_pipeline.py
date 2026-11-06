import unittest
from pathlib import Path

from src.normalizer import (
    clean_price_cell,
    fix_thai_pdf_text,
    parse_report_date,
    standardize_province,
    validate_record,
)
from src.parser import parse_pdf


class TestDITRicePipeline(unittest.TestCase):
    def test_fix_thai_pdf_text(self):
        corrupted = "ข้ำวเปลือกเจ้ำ นำปี บำท/ตัน ประจ่ำวันที ก ำแพงเพชร ล ำพูน"
        cleaned = fix_thai_pdf_text(corrupted)
        self.assertIn("ข้าวเปลือกเจ้า", cleaned)
        self.assertIn("นาปี", cleaned)
        self.assertIn("บาท/ตัน", cleaned)
        self.assertIn("ประจำวันที่", cleaned)
        self.assertIn("กำแพงเพชร", cleaned)
        self.assertIn("ลำพูน", cleaned)

        # Compound tone mark and prefix fixes
        self.assertEqual(fix_thai_pdf_text("อ ำนำจเจริญ"), "อำนาจเจริญ")
        self.assertEqual(fix_thai_pdf_text("ล ำปำง"), "ลำปาง")
        self.assertEqual(fix_thai_pdf_text("หนองบัวล ำภู"), "หนองบัวลำภู")

    def test_clean_price_cell(self):
        # Range with comma and extra spaces
        min_p, max_p = clean_price_cell("8 ,850 - 9,500")
        self.assertEqual((min_p, max_p), (8850.0, 9500.0))

        # Broken thousand digit
        min_p, max_p = clean_price_cell("1 0,500 - 12,900")
        self.assertEqual((min_p, max_p), (10500.0, 12900.0))

        # Space separated duplicate
        min_p, max_p = clean_price_cell("9,800 9,800")
        self.assertEqual((min_p, max_p), (9800.0, 9800.0))

        # Single price
        min_p, max_p = clean_price_cell("9,300")
        self.assertEqual((min_p, max_p), (9300.0, 9300.0))

        # Dash / empty
        self.assertEqual(clean_price_cell("-"), (None, None))
        self.assertEqual(clean_price_cell("- -"), (None, None))
        self.assertEqual(clean_price_cell("—"), (None, None))
        self.assertEqual(clean_price_cell(""), (None, None))

    def test_parse_report_date(self):
        text = "ภาวะตลาดสินค้าข้าว ประจำวันที่ 5 พฤศจิกายน 2569"
        d_str, day, month, year = parse_report_date(text)
        self.assertEqual(d_str, "2026-11-05")
        self.assertEqual(day, 5)
        self.assertEqual(month, 11)
        self.assertEqual(year, 2026)

        # Range text (picks last date)
        range_text = "ประจำวันที่ 29 - 30 เมษายน - 1 พฤษภาคม 2567"
        d_str2, day2, month2, year2 = parse_report_date(range_text)
        self.assertEqual(d_str2, "2024-05-01")

        # Filename DDMMYY
        d_str3, _, _, _ = parse_report_date("", filename="010567.pdf")
        self.assertEqual(d_str3, "2024-05-01")

    def test_standardize_province(self):
        self.assertEqual(standardize_province("จังหวัดพระนครศรีอยุธยา"), "Phra Nakhon Si Ayutthaya")
        self.assertEqual(standardize_province("นครสวรรค์"), "Nakhon Sawan")
        self.assertEqual(standardize_province("อุบลราชธานี"), "Ubon Ratchathani")
        self.assertIsNone(standardize_province("ไม่ระบุ"))

    def test_validate_record(self):
        valid_rec = {
            "report_date": "2026-11-05",
            "section": "PaddyRice",
            "min_price": 9000.0,
            "max_price": 9500.0,
        }
        ok, msg = validate_record(valid_rec)
        self.assertTrue(ok)

        invalid_price = {
            "report_date": "2026-11-05",
            "section": "PaddyRice",
            "min_price": 10000.0,
            "max_price": 9500.0,
        }
        ok2, msg2 = validate_record(invalid_price)
        self.assertFalse(ok2)

    def test_parse_sample_pdf(self):
        from src.config import DEDUPLICATION_KEY
        import pandas as pd

        for sample_path in [
            Path("data/pdf/2026/11/20261105160852_7171.pdf"),
            Path("data/pdf/2024/05/010567.pdf"),
        ]:
            if sample_path.exists():
                records = parse_pdf(sample_path)
                self.assertGreater(len(records), 100)
                sections = {r["section"] for r in records}
                self.assertIn("PaddyRice", sections)
                self.assertIn("MilledRice", sections)
                self.assertIn("OtherRice", sections)

                df = pd.DataFrame(records)
                # Verify zero duplicates on unique composite key
                self.assertEqual(df.duplicated(subset=DEDUPLICATION_KEY).sum(), 0)
                # Verify no suspicious min_price <= 10 (1.0 bug eliminated)
                self.assertEqual((df["min_price"] <= 10.0).sum(), 0)

        # Check all 7 target provinces across datasets
        p2024 = parse_pdf("data/pdf/2024/05/010567.pdf")
        p2026 = parse_pdf("data/pdf/2026/11/20261105160852_7171.pdf")
        df_all = pd.DataFrame(p2024 + p2026)
        all_provs = set(df_all["province"].dropna())
        target_provinces = [
            "Phra Nakhon Si Ayutthaya",
            "Surin",
            "Si Sa Ket",
            "Buriram",
            "Roi Et",
            "Amnat Charoen",
            "Lampang",
        ]
        for tp in target_provinces:
            self.assertIn(tp, all_provs)


if __name__ == "__main__":
    unittest.main()

