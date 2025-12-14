"""
Statement ingestion: confirm transactions before writing to DB.

notes:
- PDF parsing can be noisy and may return transaction objects that don't yet have a `category`.
- Downstream (DB insert, anomaly detection, summaries) expects every transaction to have a category.
- So we "normalise" here by ensuring a `category` attribute exists (default: "Uncategorised"),
  and (optionally) running an auto-categoriser when provided.
"""

from __future__ import annotations

from typing import Callable, List, Optional

from finance_agent.tools.pdf_statement import StatementTx


# A categoriser takes (merchant, amount) and returns a category string.
Categoriser = Callable[[str, float], str]


def _ensure_category(t: StatementTx, categoriser: Optional[Categoriser] = None) -> StatementTx:
    """
    Ensure the transaction has a `category` attribute.

    - If the StatementTx dataclass includes category, this will preserve it.
    - If not (older StatementTx), we attach the attribute dynamically.
    - If still "Uncategorised" and a categoriser is provided, we call it.
    """
    # Defensive: some versions of StatementTx might not have `category`
    if not hasattr(t, "category") or getattr(t, "category", None) in (None, ""):
        setattr(t, "category", "Uncategorised")

    # Optional auto-categorisation hook
    if categoriser is not None and getattr(t, "category", "Uncategorised") == "Uncategorised":
        try:
            setattr(t, "category", str(categoriser(getattr(t, "merchant", ""), float(getattr(t, "amount", 0.0)))))
        except Exception:
            # Don't fail ingestion just because categorisation failed
            pass

    return t


def confirm_statement_transactions(
    txs: List[StatementTx],
    categoriser: Optional[Categoriser] = None,
) -> List[StatementTx]:
    """
    Interactive confirmation:
    - show candidates
    - let user approve all, or approve selected

    Also normalises each tx so downstream code can safely use tx.category.
    """
    if not txs:
        print("No transactions detected in the PDF.\n")
        return []

    # Normalise upfront (so display + downstream are consistent)
    txs = [_ensure_category(t, categoriser=categoriser) for t in txs]

    print(f"\nFound {len(txs)} candidate transactions.\n")
    for i, t in enumerate(txs[:20], start=1):
        cat = getattr(t, "category", "Uncategorised")
        print(f"{i:>2}. {t.date} | £{t.amount:.2f} | {t.merchant} | {cat}")

    if len(txs) > 20:
        print(f"... showing first 20 of {len(txs)}\n")

    choice = input("\nType 'all' to add all, 'n' to cancel, or enter numbers (e.g. 1,2,5): ").strip().lower()

    if choice in {"n", "no", "cancel", "quit"}:
        return []

    if choice == "all":
        return txs

    idxs: List[int] = []
    for part in choice.split(","):
        part = part.strip()
        if part.isdigit():
            idxs.append(int(part))

    selected: List[StatementTx] = []
    for i in idxs:
        if 1 <= i <= len(txs):
            selected.append(txs[i - 1])

    # Normalise again (in case selection list is used elsewhere)
    return [_ensure_category(t, categoriser=categoriser) for t in selected]
