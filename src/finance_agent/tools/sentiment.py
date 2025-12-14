"""
Market sentiment summariser.

Takes headlines and asks the LLM to:
- cluster themes
- assign bullish/bearish/mixed
- explain rationale
"""

from __future__ import annotations
from typing import List


def build_sentiment_prompt(title: str, headlines: List[str]) -> str:
    h = "\n".join([f"- {x}" for x in headlines[:12]]) if headlines else "- (no headlines)"

    return f"""
        You are a finance assistant.

        {title}

        Headlines:
        {h}

        Task:
        1) Summarise the main themes (3–5 bullets)
        2) Overall sentiment: choose ONE of [Bullish, Bearish, Mixed/Uncertain]
        3) Give a short rationale (2–4 bullets)
        4) List what to watch next (3 bullets)

        Rules:
        - Use only the provided headlines.
        - If headlines are weak, say "Mixed/Uncertain" and explain.
        - Keep it short and clear.
    """
