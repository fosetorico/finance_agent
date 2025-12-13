"""
Simple anomaly detection rules for finance transactions.

- Uses your own history (avg spend)
- Flags new merchants with non-trivial spend
- Flags unusually large transactions
"""

def detect_anomalies(db, merchant: str, amount: float) -> list[str]:
    reasons = []

    if amount >= 100:
        reasons.append("High amount (>= £100).")

    if hasattr(db, "merchant_exists") and not db.merchant_exists(merchant) and amount >= 40:
        reasons.append("New merchant and amount >= £40.")

    if hasattr(db, "avg_amount"):
        avg_amt = db.avg_amount()
        if avg_amt > 0 and amount >= (avg_amt * 3):
            reasons.append(f"Amount is >= 3x your average transaction (£{avg_amt:.2f}).")

    return reasons
