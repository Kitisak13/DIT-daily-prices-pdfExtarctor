import os
import re
from pathlib import Path
from typing import Dict, List, Optional
import requests
import urllib3

from src.config import (
    DIT_BASE_URL,
    DIT_CALENDAR_API,
    DIT_CONTENT_ID,
    DIT_HEADERS,
    PDF_DIR,
)

# Suppress insecure request warnings if cert validation is bypassed for gov portal
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


def fetch_calendar_events(start_date: str, end_date: str) -> List[Dict]:
    """Query DIT FullCalendar API for rice reports between start_date and end_date (YYYY-MM-DD).

    Returns a list of event dictionaries containing title, start, end, url.
    """
    params = {
        "contentId": DIT_CONTENT_ID,
        "top": 0,
        "lang": "th-TH",
        "start": start_date,
        "end": end_date,
    }

    try:
        response = requests.get(
            DIT_CALENDAR_API,
            params=params,
            headers=DIT_HEADERS,
            verify=False,
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        events = data.get("result", {}).get("events", [])
        return events
    except Exception as e:
        print(f"[Error] Failed to fetch calendar events from {start_date} to {end_date}: {e}")
        return []


def download_report(event: Dict) -> Optional[Path]:
    """Download a single PDF report based on an event dictionary and store it in

    /data/pdf/YYYY/MM/<filename>.pdf.
    """
    url = event.get("url")
    if not url:
        return None

    if not url.startswith("http"):
        url = DIT_BASE_URL + url

    # Determine date for folder hierarchy (YYYY/MM)
    start_date = event.get("start")
    if start_date and re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
        year, month, _ = start_date.split("-")
    else:
        # Fallback to current year/month
        year = "unknown"
        month = "unknown"

    target_dir = PDF_DIR / year / month
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = Path(url).name
    target_file = target_dir / filename

    if target_file.exists() and target_file.stat().st_size > 0:
        # Already downloaded
        return target_file

    try:
        r = requests.get(url, headers=DIT_HEADERS, verify=False, timeout=30)
        r.raise_for_status()
        with open(target_file, "wb") as f:
            f.write(r.content)
        print(f"[Downloaded] {filename} ({len(r.content)} bytes) -> {target_file}")
        return target_file
    except Exception as e:
        print(f"[Error] Failed to download {url}: {e}")
        return None


def crawl_date_range(start_date: str, end_date: str) -> List[Path]:
    """Discover and download all PDF reports in the given date range.

    Returns a list of local PDF paths.
    """
    events = fetch_calendar_events(start_date, end_date)
    print(f"Found {len(events)} report events between {start_date} and {end_date}.")
    downloaded_paths = []
    for event in events:
        p = download_report(event)
        if p:
            downloaded_paths.append(p)
    return downloaded_paths

