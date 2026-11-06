# DIT Rice Market Price Extraction Pipeline

Automated pipeline for downloading daily rice market price reports from the Department of Internal Trade (DIT, Thailand) and extracting them into structured datasets (Daily CSVs, Master CSV, and Excel).

## Features

- **Automated Crawler (`crawler.py`)**: Fetches calendar event metadata and PDF download links via DIT's FullCalendar API (`https://www.dit.go.th/api/FullCalendar/GetsFullCalendar`).
- **Robust Local PDF Parser (`parser.py`)**:
  - Handles legacy Thai font glyph encoding issues (`THSarabunPSK` with `WinAnsiEncoding` where vowels like `า` map to `ำ`).
  - Cleans price ranges (removes broken spaces inside numbers, handles missing commas, cleans `1 0,500` -> `10500`, etc.).
  - Automatically identifies report date from document title (Thai Buddhist era to ISO-8601 `YYYY-MM-DD`).
  - Dynamically classifies records into **PaddyRice** (ข้าวเปลือก), **MilledRice** (ข้าวสารขายส่ง), and **OtherRice** (รำข้าว, แป้ง, ขายปลีก).
- **Quality & Deduplication Engine (`normalizer.py` & `exporter.py`)**:
  - Standardizes 77 Thai provinces to English.
  - Enforces `min_price <= max_price`.
  - Deduplicates on composite key `(report_date, section, product_name, province, grade)`.
- **Exports**:
  - Daily CSV: `data/extracted/csv/YYYY-MM-DD.csv`
  - Master CSV: `rice_prices_master.csv`
  - Master Excel: `data/excel/rice_prices_master.xlsx` (Sheets: `PaddyRice`, `MilledRice`, `OtherRice`)
- **Agentic AI Fallback (`ai_fallback.py`)**: Uses Google GenAI (Gemini) as an optional fallback if a PDF is scanned or cannot be parsed by `pdfplumber`.

## Directory Structure

```
DIT Rice Prices/
├── data/
│   ├── pdf/YYYY/MM/          # Downloaded PDF reports
│   ├── extracted/csv/        # Daily CSVs (YYYY-MM-DD.csv)
│   ├── excel/                # Master Excel workbook
│   └── logs/
├── src/
│   ├── config.py             # Paths, schemas, province mappings
│   ├── crawler.py            # DIT FullCalendar scraper & PDF downloader
│   ├── normalizer.py         # Thai font fixer, price/date normalizer
│   ├── parser.py             # Content-aware multi-page PDF table parser
│   ├── exporter.py           # Master CSV & Excel generator
│   └── ai_fallback.py        # Gemini API fallback extractor
├── tests/
│   └── test_pipeline.py      # Automated unit tests
├── main.py                   # CLI Orchestrator
├── requirements.txt
├── AGENTS.md
└── README.md
```

## Usage

### 1. Process all already-downloaded local PDFs
```bash
python main.py --process-local
```

### 2. Crawl and process the latest N days
```bash
python main.py --latest 7
```

### 3. Crawl a specific date range
```bash
python main.py --date-from 2026-10-01 --date-to 2026-11-06
```

### 4. Optional: Run with Gemini Agentic AI
```bash
python main.py --process-local --use-ai --api-key YOUR_GEMINI_KEY
# Or set GEMINI_API_KEY environment variable
```

### 5. Run automated tests
```bash
python -m unittest tests/test_pipeline.py
```

