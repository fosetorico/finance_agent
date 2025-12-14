"""
News tool for fetching live finance and AI headlines.

Uses a public search API (DuckDuckGo via requests).
Designed to be MCP-compatible later.
"""

import requests


# Base URL for DuckDuckGo Instant Answer API
DDG_API = "https://api.duckduckgo.com/"


def fetch_news(query: str, max_results: int = 5) -> list[str]:
    """
    Fetch news headlines for a given query.

    Args:
        query: Search query (e.g. 'finance news', 'AI news')
        max_results: Max number of results to return

    Returns:
        List of headline strings
    """
    params = {
        "q": query,
        "format": "json",
        "no_redirect": 1,
        "no_html": 1,
        "skip_disambig": 1,
    }

    response = requests.get(DDG_API, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    headlines = []

    # Extract related topics as lightweight "news"
    for item in data.get("RelatedTopics", []):
        if isinstance(item, dict) and "Text" in item:
            headlines.append(item["Text"])
        if len(headlines) >= max_results:
            break

    return headlines


def get_finance_news() -> list[str]:
    """Fetch latest finance-related news."""
    return fetch_news("latest finance market news")


def get_ai_news() -> list[str]:
    """Fetch latest AI / tech-related news."""
    return fetch_news("latest artificial intelligence news")
