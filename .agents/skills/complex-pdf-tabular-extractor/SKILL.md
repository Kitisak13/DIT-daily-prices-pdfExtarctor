---
name: complex-pdf-tabular-extractor
description: >-
  Guides the extraction of structured tabular data from complex, multi-column, or non-standard
  government/enterprise PDF reports using PyMuPDF coordinate-based parsing, dynamic calendar
  matrix bounding, font glyph normalization, and safe backfill pipelines. Use when standard
  PDF table libraries fail, produce split numbers, or when documents contain weekly matrix tables.
---

# Complex PDF Tabular Data Extraction & Pipeline Architecture

This skill provides production-grade patterns for parsing complex tabular reports from PDFs where standard table extractors (like `pdfplumber`, `tabula`, or basic OCR) fail due to lack of vector borders, split coordinate tokens, or complex non-Latin typography.

---

## 1. When to Use Coordinate-Based PyMuPDF Over Table Libraries

| Scenario | Standard Libraries (`pdfplumber` / `tabula`) | Coordinate-Based PyMuPDF (`fitz.get_text("words")`) |
| :--- | :--- | :--- |
| **No explicit table borders** | Splits or merges columns incorrectly | Precise bounding using column header centroids |
| **Separated digits in font encoding** (e.g. `1,` and `950`) | Treats as two distinct table columns | Groupable by bounding box X/Y proximity |
| **Complex non-Latin scripts** (e.g. Thai `THSarabunPSK`) | Tone marks and floating vowels break alignment | Pre-normalized via custom glyph repair dictionaries |
| **High throughput backfill** (thousands of files) | High memory overhead, leak-prone | Sub-second parsing, strictly managed file handles |

---

## 2. Core Architecture Patterns

### Pattern A: Word Extraction & Line Grouping
Extract raw words `(x0, y0, x1, y1, text, block_no, line_no, word_no)` from PyMuPDF and cluster into horizontal lines using rounded Y-coordinates (e.g., tolerance of 1.5–2.0 pt):

```python
import fitz
from collections import defaultdict

with fitz.open(pdf_path) as doc:
    page = doc[page_index]
    words = page.get_text("words")

# Cluster words by vertical position
lines = defaultdict(list)
for w in words:
    # Round Y coordinate to cluster words on the same baseline
    y_approx = round(w[1] / 2.0) * 2.0
    lines[y_approx].append(w)
```

### Pattern B: Dynamic Calendar Matrix Column Bounding
In weekly matrix tables where columns represent days (Monday–Friday) plus summary columns ("Last Week", "This Week"):

1. **Locate Day Headers**: Scan header line for day labels and determine center coordinates:
   ```python
   col_centers = {wd: (w[0] + w[2]) / 2.0 for wd, w in detected_headers.items()}
   ```
2. **Compute Midpoints for Column Spans**:
   ```python
   # col_bounds[i] = (x_min, x_max) derived from half-distance between adjacent headers
   ```
3. **Right-Bound on Summary Column**:
   Use the center coordinate of the next summary header (e.g., "สัปดาห์นี้") as the absolute `x_max` for the last day column to prevent weekly summary numbers from leaking into daily records.
4. **Future Day Boundary Guard**:
   Restrict target weekday extraction to:
   ```python
   max_allowed_wd = min(report_weekday, 4)
   target_wds = list(range(max_allowed_wd + 1))
   ```
   Never extract columns whose weekday is in the future relative to the document publication date.

### Pattern C: Font Artifact & Non-Latin Glyph Normalization
Legacy PDF printers (like Thai Government Sarabun fonts) often render tone marks, Sara Am (`ำ`), or vowel shifts as isolated character codes:

1. **Pre-replace known compounds** before parsing regex:
   ```python
   # Replace split vowel glyphs with correct Unicode codepoints
   text = text.replace("อ ำนำจเจริญ", "อำนาจเจริญ")
   ```
2. **Protect genuine characters** using temporary placeholders before applying general normalization passes.
3. **Regex Digit Cleansing**:
   ```python
   # Remove internal formatting spaces, dashes, and currency marks
   val = re.sub(r"[^\d.]", "", raw_cell)
   ```

### Pattern D: Backward Peek for Misaligned Multiline Cells
In dense tables, sub-variant prices (or "New Crop" labels) may render 1.5–3.0 pt above or below the product label due to font leading:

```python
# If target column is empty on current row, check preceding row within 4pt vertical delta
if not col_words and row_idx > 0 and (current_y - prev_y <= 4.0):
    prev_row_words = lines[prev_y]
    # Check if preceding line contained numeric values without a product label
    if is_price_like(prev_row_words):
        col_words = prev_row_words
```

### Pattern E: Deduplication & Composite Unique Keys
Never rely on single primary keys for aggregated price datasets. Maintain a strict composite key:

$$\text{Key} = (\text{report\_date}, \text{section}, \text{product\_name}, \text{province}, \text{grade})$$

When aggregating historical datasets:
```python
master_df = pd.concat([existing_df, new_df], ignore_index=True)
master_df.drop_duplicates(subset=DEDUPLICATION_KEY, keep="last", inplace=True)
```
Always sort files chronologically before batch processing so `keep="last"` correctly prioritizes subsequent amendments.

### Pattern F: Safe Weekly Representative Backfilling
To backfill multiple years efficiently:
1. **Fetch One File Per Week**: Group calendar events by ISO `(year, week)` and pick the latest available publishing day (handles holidays automatically).
2. **Query Expansion with Boundary Guard**:
   When expanding API query windows (`end_date + 6 days`) to avoid clipping the final week, enforce:
   ```python
   monday_of_week = (event_date - timedelta(days=event_date.weekday())).date()
   if monday_of_week > requested_end_date:
       continue  # Exclude next week if requested end_date was already a Friday
   ```

### Pattern G: Memory & OS Resource Safety
For large batch jobs:
1. **Always use Context Managers**: `with fitz.open(pdf_path) as doc:`
2. **Fast Filename Pre-Check**: Parse date from filename regex before opening the PDF document stream during sorting phases to avoid duplicate I/O.

