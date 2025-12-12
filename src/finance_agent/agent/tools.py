def get_db_context(db):
    total = db.total_spend()
    by_cat = db.spend_by_category()
    recent = db.recent_transactions(limit=10)

    by_cat_text = "\n".join(
        [f"- {cat}: £{amt:.2f}" for cat, amt in by_cat]
    ) if by_cat else "No data yet."

    recent_text = "\n".join(
        [f"- {d} | {m} | £{a:.2f} | {c}" for d, m, a, c in recent]
    ) if recent else "No data yet."

    return f"""
        Structured finance data:
        Total spend: £{total:.2f}

        Spend by category:
        {by_cat_text}

        Recent transactions:
        {recent_text}
    """
