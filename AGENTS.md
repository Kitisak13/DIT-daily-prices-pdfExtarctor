# AGENTS.md

## Project Name

DIT Rice Market Price Extraction Pipeline

## Objective

Build an autonomous agent workflow that downloads public rice market reports from the Department of Internal Trade (Thailand) and converts all PDF reports into structured datasets suitable for storage in databases, Excel files, or Google Sheets.

Source Website:
https://www.dit.go.th/th/278062/

The reports contain historical daily rice market prices published by the Department of Internal Trade (DIT).

The final objective is to create a complete historical rice price database covering all available publication dates.

---

# High-Level Workflow

Agent responsibilities:

1. Discover and download new PDF reports.
2. Store PDF files in the document repository.
3. Extract structured data from every PDF.
4. Classify data into predefined sections.
5. Normalize extracted values.
6. Validate extraction quality.
7. Export data into:
   - Excel
   - Google Sheets
   - Database tables

---

# PDF Structure

Each report generally contains four pages and three major sections.

## Section 1: Paddy Rice

Pages: 1-2

Contains paddy rice prices by province.

Examples:

- Ordinary Paddy Rice
- Jasmine Paddy Rice
- Pathum Thani Paddy Rice
- Glutinous Paddy Rice
- Mixed Glutinous Paddy Rice

Typical fields:

- Province
- Rice Type
- Min Price
- Max Price
- Report Date

Unit:

THB per ton

---

## Section 2: Milled Rice

Pages: 3

Contains wholesale rice prices.

Examples:

- White Rice 100% Grade 1
- White Rice 100% Grade 2
- White Rice 5%
- White Rice 10%
- Parboiled Rice
- Jasmine Rice
- Pathum Thani Rice
- Broken Rice

Typical fields:

- Product Name
- Quality Grade
- Min Price
- Max Price
- Report Date

Unit:

THB per 100 kg

---

## Section 3: Other Rice-related Prices

Pages: 4

Contains additional market prices.

Examples:

- Rice Bran
- Rice Flour
- Retail Rice Prices
- Rice Sacks
- Rice By-products
- Domestic Consumer Prices

Typical fields:

- Product Name
- Product Category
- Min Price
- Max Price
- Report Date

Units may vary:

- THB per 100 kg
- THB per 15 kg
- THB per item
- THB per bag

---

# Required Output Schema

All extracted records must be normalized into the following format.

| Column               | Description                        |
| -------------------- | ---------------------------------- |
| report_date          | Report publication date            |
| section              | PaddyRice / MilledRice / OtherRice |
| category             | Product category                   |
| product_name         | Product name                       |
| province             | Province name (nullable)           |
| grade                | Product grade if available         |
| min_price            | Minimum price                      |
| max_price            | Maximum price                      |
| unit                 | Price unit                         |
| source_file          | Original PDF filename              |
| page_number          | Page number extracted from         |
| extraction_timestamp | UTC timestamp                      |

---

# Data Normalization Rules

## Numbers

Convert:

1,530 → 1530

17,300 → 17300

Remove:

- commas
- extra spaces

Store as numeric values.

---

## Empty Values

Treat the following as NULL:

- "-"
- "—"
- ""
- blank cells

Do not convert missing values to zero.

---

## Dates

Extract report date from title.

Example:

ภาวะตลาดสินค้าข้าว ประจำวันที่ 4 พฤศจิกายน 2569

Convert to:

2026-11-04

Store in ISO-8601 format.

---

## Province Standardization

Convert province names into a consistent format.

Example:

จังหวัดพระนครศรีอยุธยา

Store as:

Phra Nakhon Si Ayutthaya

Maintain a province mapping dictionary.

---

# Classification Rules

Agent must automatically classify records.

## PaddyRice

Keywords:

- ข้าวเปลือก
- หอมมะลิ
- ปทุมธานี
- เหนียว

Output section:

PaddyRice

---

## MilledRice

Keywords:

- ข้าวขาว
- ข้าวนึ่ง
- ข้าวหอมมะลิ
- ข้าวปทุมธานี
- ปลายข้าว

Output section:

MilledRice

---

## OtherRice

Keywords:

- รำข้าว
- แป้งข้าว
- กระสอบป่าน
- ราคาขายปลีก

Output section:

OtherRice

---

# Data Quality Validation

The agent must verify:

## Price Validation

min_price <= max_price

If not:

Flag record for review.

---

## Date Validation

Date must exist.

If date cannot be extracted:

Reject document.

---

## Duplicate Detection

Unique key:

(report_date,
section,
product_name,
province,
grade)

Duplicate rows must not be inserted.

---

# Storage Structure

Recommended folder structure:

/data
/pdf
/2026
/11
report.pdf

    /extracted
        /csv

    /excel

    /logs

---

# Output Files

Generate:

## Daily CSV

YYYY-MM-DD.csv

Example:

2026-11-04.csv

---

## Master Dataset

rice_prices_master.csv

Append all historical records.

---

## Excel Workbook

Sheets:

- PaddyRice
- MilledRice
- OtherRice

---

# Error Handling

If extraction confidence is low:

1. Save raw text.
2. Save screenshot.
3. Log issue.
4. Continue processing remaining records.

Pipeline must never stop because of a single malformed PDF.

---

# Success Criteria

The agent is considered successful when:

- 100% of PDF files are downloaded.
- Report date is extracted correctly.
- Data is classified into the correct section.
- Prices are stored in normalized format.
- No duplicate records exist.
- Historical data can be queried by date, product, and province.

End of AGENTS.md
