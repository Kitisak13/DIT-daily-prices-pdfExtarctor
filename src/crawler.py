import os
import re
from datetime import datetime, timedelta
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


def filter_weekly_latest_events(events: List[Dict], max_end_date: Optional[str] = None) -> List[Dict]:
    """Group calendar events by ISO year and week, and pick the latest available
    event in each week (e.g. Friday, or Thursday/Wednesday if holidays occur).
    This enables historical backfill using only 1 representative file per week.

    If max_end_date is provided, weeks whose Monday falls after max_end_date are excluded.
    """
    max_end_dt = None
    if max_end_date:
        try:
            max_end_dt = datetime.strptime(max_end_date, "%Y-%m-%d").date()
        except Exception:
            pass

    weeks = {}
    for ev in events:
        start_str = ev.get("start", "")
        date_part = start_str.split("T")[0] if start_str else ""
        # Check for invalid year (e.g. 0001-01-01) and recover from title
        if not date_part or date_part.startswith("000") or int(date_part.split("-")[0]) < 2000:
            title = ev.get("title", "")
            m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", title)
            if m:
                date_part = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
                ev["start"] = date_part
            else:
                continue

        try:
            dt = datetime.strptime(date_part, "%Y-%m-%d")
            # Monday of the event's week
            monday_dt = (dt - timedelta(days=dt.weekday())).date()
            if max_end_dt and monday_dt > max_end_dt:
                continue

            year_week = dt.isocalendar()[:2]  # (iso_year, iso_week)
            if year_week not in weeks or dt > weeks[year_week][0]:
                weeks[year_week] = (dt, ev)
        except Exception:
            continue

    selected = [item[1] for item in sorted(weeks.values(), key=lambda x: x[0])]
    return selected


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
    if not start_date or start_date.startswith("000") or int(start_date.split("-")[0]) < 2000:
        title = event.get("title", "")
        m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", title)
        if m:
            start_date = f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    if start_date and re.match(r"^\d{4}-\d{2}-\d{2}", start_date):
        date_part = start_date.split("T")[0]
        year, month, _ = date_part.split("-")
    else:
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


def crawl_date_range(start_date: str, end_date: str, weekly_only: bool = False) -> List[Path]:
    """Discover and download PDF reports in the given date range.

    If weekly_only=True, only downloads the last available report of each week.
    Automatically extends query range by 6 days when weekly_only=True to prevent
    boundary clipping of the last week.
    Returns a list of local PDF paths.
    """
    query_end = end_date
    if weekly_only:
        try:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
            query_end = (end_dt + timedelta(days=6)).strftime("%Y-%m-%d")
        except Exception:
            pass

    events = fetch_calendar_events(start_date, query_end)
    print(f"Found {len(events)} report events between {start_date} and {query_end}.")

    if weekly_only:
        events = filter_weekly_latest_events(events, max_end_date=end_date)
        print(f"Filtered to {len(events)} weekly representative reports (last published day of each week).")

    downloaded_paths = []
    from concurrent.futures import ThreadPoolExecutor, as_completed

    # Download concurrently with a polite worker pool (8 workers)
    with ThreadPoolExecutor(max_workers=8) as executor:
        future_to_event = {executor.submit(download_report, ev): ev for ev in events}
        for future in as_completed(future_to_event):
            try:
                p = future.result()
                if p:
                    downloaded_paths.append(p)
            except Exception as e:
                print(f"[Download Exception]: {e}")
    return downloaded_paths
