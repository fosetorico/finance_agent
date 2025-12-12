import json
from datetime import datetime

from finance_agent.agent.categorizer import rule_based_category  # from Phase 3.1
from finance_agent.domain.models import Transaction


def _looks_like_anomaly(db, merchant: str, amount: float) -> list[str]:
    """
    Simple anomaly checks for receipts.
    Returns a list of human-readable reasons (empty means no anomaly).
    """
    reasons = []

    # Rule 1: high amount
    if amount >= 100:
        reasons.append("High amount (>= £100).")

    # Rule 2: new merchant + medium/high amount
    if not db.merchant_exists(merchant) and amount >= 40:
        reasons.append("New merchant and amount >= £40.")

    # Rule 3 (optional simple baseline): much higher than average
    avg_amt = db.avg_amount()
    if avg_amt > 0 and amount >= (avg_amt * 3):
        reasons.append(f"Amount is >= 3x your average transaction (£{avg_amt:.2f}).")

    return reasons


def confirm_transaction(parsed_json: str, db) -> Transaction | None:
    """
    Human-in-the-loop confirmation with:
    - anomaly warnings
    - category auto-suggestion + ask if unsure
    """
    try:
        data = json.loads(parsed_json)
    except json.JSONDecodeError:
        print("\n❌ LLM output was not valid JSON. Receipt not saved.")
        print("Raw output:\n", parsed_json)
        return None

    date_str = data.get("date")
    merchant = (data.get("merchant") or "").strip()
    amount = float(data.get("total_amount", 0.0))
    llm_category = (data.get("category") or "").strip()

    # --- Basic validation ---
    if not merchant or amount <= 0 or not date_str:
        print("\n❌ Receipt parse looks incomplete. Not saving.")
        print("Parsed:", data)
        return None

    # --- Auto-category using rules (fast + consistent) ---
    rule_cat = rule_based_category(merchant)

    # Decide if we are "unsure"
    unsure = (
        (not llm_category)
        or (llm_category.lower() == "other")
        or (rule_cat is not None and rule_cat != llm_category)
    )

    final_category = llm_category if llm_category else "Other"

    # If unsure, ask user to choose
    if unsure:
        print("\n🤔 Category uncertainty detected:")
        if rule_cat:
            print(f"- Rule-based suggestion: {rule_cat}")
        if llm_category:
            print(f"- LLM suggestion: {llm_category}")
        else:
            print("- LLM did not return a category.")

        typed = input("Enter category to use (or press Enter to accept rule/LLM): ").strip()
        if typed:
            final_category = typed
        else:
            final_category = rule_cat or final_category

    # --- Anomaly detection ---
    anomaly_reasons = _looks_like_anomaly(db, merchant, amount)

    print("\n🧾 Proposed transaction:")
    print(f"Date: {date_str}")
    print(f"Merchant: {merchant}")
    print(f"Amount: £{amount:.2f}")
    print(f"Category: {final_category}")

    if anomaly_reasons:
        print("\n⚠️ Possible anomaly detected:")
        for r in anomaly_reasons:
            print(f"- {r}")

    confirm = input("\nSave this transaction? (yes/no): ").strip().lower()
    if confirm not in ("y", "yes"):
        print("❌ Transaction discarded.\n")
        return None

    return Transaction(
        date=date_str,
        merchant=merchant,
        amount=amount,
        category=final_category,
    )

