"""
Decides what is worth saving to long-term memory.

Rule of thumb:
- Save preferences, goals, recurring constraints, and stable facts
- Do NOT save random one-off chatter
"""

def should_store_memory(user_text: str, assistant_text: str) -> bool:
    t = (user_text + " " + assistant_text).lower()

    signals = [
        "budget", "limit", "alert", "notify", "goal", "every month",
        "i prefer", "remind me", "from now on", "watch out for",
        "overspend", "subscription", "rent", "saving"
    ]

    return any(s in t for s in signals)
