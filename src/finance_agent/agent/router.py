def classify_intent(user_input: str) -> str:
    """
    Decide what kind of task the user is asking for.

    Returns:
        - "db"        → factual queries (totals, summaries, lists)
        - "llm"       → advice, planning, explanations
        - "hybrid"    → needs both facts + reasoning
    """

    text = user_input.lower()

    db_keywords = [
        "total", "how much", "spent", "spend",
        "summary", "monthly", "transactions",
        "top merchants", "list"
    ]

    llm_keywords = [
        "should i", "how can i", "advice",
        "recommend", "plan", "improve",
        "save", "budget"
    ]

    web_keywords = [
        "news", "latest", "inflation", "interest rate",
        "exchange rate", "fx", "market", "headline",
        "trending", "economy", "financial", "stock",
        "market news", "economy news", "financial news",
        "stock market news", "economy news", "financial news"
    ]

    # If it clearly asks for numbers/facts
    if any(k in text for k in db_keywords) and not any(k in text for k in llm_keywords):
        return "db"

    # If it clearly asks for advice only
    if any(k in text for k in llm_keywords) and not any(k in text for k in db_keywords):
        return "llm"

    if any(k in text for k in web_keywords):
        return "web"

    # Otherwise, assume it needs both
    return "hybrid"
