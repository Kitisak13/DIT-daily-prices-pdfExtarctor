import os
import json
from pathlib import Path
from typing import Dict, List, Optional


def extract_with_gemini(pdf_path: str | Path, api_key: Optional[str] = None) -> List[Dict]:
    """Fallback / Agentic AI extractor using Google GenAI (Gemini API).

    Extracts rice market price tables directly from the PDF if pdfplumber fails.
    """
    key = api_key or os.environ.get("GEMINI_API_KEY")
    if not key:
        print("[AI Fallback] GEMINI_API_KEY is not set. Please set the environment variable or pass --api-key.")
        return []

    try:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=key)
        pdf_path = Path(pdf_path)

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        prompt = """
You are an expert data extractor for Thailand Department of Internal Trade (DIT) Rice Market Price Reports.
Extract all price records from this PDF into a structured JSON array of objects.

Each object must follow this exact schema:
- report_date: string (YYYY-MM-DD from document title, convert Thai Buddhist year to Gregorian e.g. 2569 -> 2026)
- section: string (one of: 'PaddyRice', 'MilledRice', 'OtherRice')
- category: string (e.g. 'ข้าวเปลือกเจ้านาปี', 'ข้าวขาว 100%', 'รำข้าว')
- product_name: string (e.g. 'ข้าวเปลือกเจ้านาปี', 'ข้าวขาว 100% ชั้น 1', 'รำข้าว - ขาว')
- province: string or null (Standard English province name, e.g. 'Nakhon Sawan', null for wholesale)
- grade: string or null (e.g. 'ข้าวใหม่' or null)
- min_price: number (numeric minimum price, null if missing/hyphen)
- max_price: number (numeric maximum price, null if missing/hyphen)
- unit: string ('THB per ton', 'THB per 100 kg', 'THB per 15 kg', etc.)
- source_file: string (original filename)
- page_number: number (page where item was found)

Return ONLY valid JSON matching this schema.
"""

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=[
                types.Part.from_bytes(
                    data=pdf_bytes,
                    mime_type="application/pdf",
                ),
                prompt,
            ],
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.0,
            ),
        )

        data = json.loads(response.text)
        if isinstance(data, list):
            return data
        elif isinstance(data, dict) and "records" in data:
            return data["records"]
        return []
    except Exception as e:
        print(f"[AI Fallback Error] {e}")
        return []

