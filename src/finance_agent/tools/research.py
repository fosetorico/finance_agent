"""
Browser-based research using MCP (Playwright).

- Takes a topic (company/product)
- Visits trusted sources (direct URLs, not search engines)
- Extracts headline-like items
- Returns a structured brief prompt for the LLM to summarise
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict
from datetime import datetime

from finance_agent.tools.trusted_news import fetch_headlines_from_url


RESEARCH_SOURCES: List[Dict[str, str]] = [
    {"source": "Reuters Markets", "url": "https://www.reuters.com/markets/"},
    {"source": "BBC Business", "url": "https://www.bbc.co.uk/news/business"},
    {"source": "Financial Times Markets", "url": "https://www.ft.com/markets"},
    {"source": "Investopedia", "url": "https://www.investopedia.com/"},
    {"source": "The Verge AI", "url": "https://www.theverge.com/artificial-intelligence"},
    {"source": "TechCrunch AI", "url": "https://techcrunch.com/tag/artificial-intelligence/"},
]


@dataclass
class Evidence:
    source: str
    url: str
    titles: List[str]


async def collect_research_evidence(mcp_agent, topic: str, max_per_source: int = 4) -> List[Evidence]:
    """
    Collect headline-like titles about a topic from several trusted sites.

    Fail-soft per site.
    """
    out: List[Evidence] = []

    for src in RESEARCH_SOURCES:
        try:
            titles = await fetch_headlines_from_url(mcp_agent, src["url"], max_items=max_per_source)
            # keep only titles that mention the topic (rough filter)
            filtered = [t for t in titles if topic.lower() in t.lower()]
            if filtered:
                out.append(Evidence(source=src["source"], url=src["url"], titles=filtered))
        except Exception:
            continue

    return out


def build_research_prompt(topic: str, evidence: List[Evidence]) -> str:
    """
    Creates a tight LLM prompt to generate a structured research brief.
    """
    now = datetime.utcnow().strftime("%Y-%m-%d")

    lines = [f"Topic: {topic}", f"Date: {now}", "", "Evidence (headlines found):"]
    if not evidence:
        lines.append("- (No matching headlines found on trusted sources)")
    else:
        for ev in evidence:
            lines.append(f"\nSource: {ev.source} ({ev.url})")
            for t in ev.titles[:6]:
                lines.append(f"- {t}")

    lines.append(
        """
Now write a concise research brief in plain English with this structure:

1) What it is (1–2 lines)
2) What’s happening right now (3–5 bullets)
3) Why it matters (2–3 bullets)
4) Key risks / watch-outs (3 bullets max)
5) What to monitor next (3 bullets max)

Rules:
- If evidence is thin, say so and avoid guessing.
- Keep it short and practical.
"""
    )

    return "\n".join(lines)
