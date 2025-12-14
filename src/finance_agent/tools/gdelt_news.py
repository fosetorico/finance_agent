from __future__ import annotations

"""
Live news fetcher using GDELT 2.1 (free, no API key).

This is a reliable fallback when search engines block automated requests.
"""

import datetime as dt
import requests


GDELT_DOC_API = "https://api.gdeltproject.org/api/v2/doc/doc"


def _today_utc_range():
    # GDELT wants YYYYMMDDHHMMSS in UTC
    now = dt.datetime.utcnow()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    return start.strftime("%Y%m%d%H%M%S"), now.strftime("%Y%m%d%H%M%S")


def fetch_latest_news(query: str, max_results: int = 5) -> list[dict]:
    """
    Fetch latest news articles matching query from today (UTC).

    Returns a list of dicts: {title, source, url, datetime}
    """
    start, end = _today_utc_range()

    params = {
        "query": query,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": max_results,
        "startdatetime": start,
        "enddatetime": end,
        "sort": "HybridRel",  # good default
    }

    r = requests.get(GDELT_DOC_API, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()

    arts = data.get("articles", []) or []
    results = []
    for a in arts[:max_results]:
        results.append(
            {
                "title": a.get("title"),
                "source": a.get("sourceCountry") or a.get("sourceCollection") or a.get("domain"),
                "url": a.get("url"),
                "datetime": a.get("seendate") or a.get("datetime"),
            }
        )
    return results


def format_headlines(items: list[dict]) -> str:
    if not items:
        return "No matching headlines found for today."
    lines = []
    for it in items:
        lines.append(f"- {it.get('title')} | {it.get('source')} | {it.get('datetime')} | {it.get('url')}")
    return "\n".join(lines)
