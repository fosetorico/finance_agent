"""
Trusted news fetcher using Browser MCP (Playwright) instead of search engines.

We visit a small set of known URLs and extract visible headline text.
This avoids DuckDuckGo bot detection issues.

Note:
- Headline extraction is heuristic (CSS selectors vary by site).
- We keep it robust by using multiple selectors and fallback to page snapshot text.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict


@dataclass
class NewsItem:
    source: str
    title: str
    url: str


# Keep a small, high-signal list. You can expand later.
FINANCE_SOURCES = [
    {"source": "Bank of England", "url": "https://www.bankofengland.co.uk/news"},
    {"source": "FCA", "url": "https://www.fca.org.uk/news/news-stories"},
    {"source": "Financial Times", "url": "https://www.ft.com/markets"},
    {"source": "Reuters Markets", "url": "https://www.reuters.com/markets/"},
    {"source": "BBC Business", "url": "https://www.bbc.co.uk/news/business"},
]

AI_SOURCES = [
    # {"source": "OpenAI", "url": "https://openai.com/news/"},
    {"source": "Google AI Blog", "url": "https://blog.google/technology/ai/"},
    {"source": "DeepMind Blog", "url": "https://deepmind.google/discover/blog/"},
    {"source": "The Verge AI", "url": "https://www.theverge.com/artificial-intelligence"},
    {"source": "TechCrunch AI", "url": "https://techcrunch.com/tag/artificial-intelligence/"},
]


async def fetch_headlines_from_url(mcp_agent, url: str, max_items: int = 5) -> List[str]:
    """
    Uses the MCP browser toolchain via the agent to:
    - navigate to a URL
    - extract headline-like text

    We keep it simple: ask the agent to use browser tools and return ONLY titles.
    """
    prompt = f"""
        Use the browser tools to visit: {url}

        Rules:
        - Do NOT keep retrying if extraction fails.
        - Use ONE attempt only:
        1) browser_navigate to the page
        2) browser_snapshot
        - From the snapshot, extract up to {max_items} headline-like titles.

        Return ONLY a bullet list of titles.
        If you can't find any titles, return exactly: ACCESS_FAILED
    """
    resp = await mcp_agent.run(prompt)
    text = (resp or "").strip()

    if "ACCESS_FAILED" in text.upper():
        return []

    # Parse bullet lines
    lines = [ln.strip("-• ").strip() for ln in text.splitlines() if ln.strip()]
    # Keep only non-empty lines
    return [ln for ln in lines if ln][:max_items]


async def fetch_trusted_news(mcp_agent, sources: List[Dict], max_per_source: int = 3) -> List[NewsItem]:
    """
    Fetch headlines from a list of trusted sources using browser MCP.

    🔧 EDIT: Fail-soft per source so one problematic site doesn't crash the whole command.
    """
    items: List[NewsItem] = []

    for src in sources:
        try:
            titles = await fetch_headlines_from_url(mcp_agent, src["url"], max_items=max_per_source)
            for t in titles:
                items.append(NewsItem(source=src["source"], title=t, url=src["url"]))
        except Exception:
            # 🔧 EDIT: Skip broken sources (cookie walls, JS-heavy, bot checks, recursion, etc.)
            continue

    return items


def format_news(items: List[NewsItem], title: str) -> str:
    if not items:
        return f"{title}\n(no headlines fetched — browser access blocked or page structure changed)\n"

    out = [title]
    for it in items[:15]:
        out.append(f"- {it.title} | {it.source} | {it.url}")
    return "\n".join(out) + "\n"
