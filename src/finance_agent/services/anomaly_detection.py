from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple, Dict
import math
from collections import defaultdict

Row = Tuple[str, str, float, str, str]  # date, merchant, amount, category, source

@dataclass
class Anomaly:
    date: str
    merchant: str
    amount: float
    category: str
    reason: str
    severity: str  # "high" | "medium" | "low"

def _mean_std(values: List[float]) -> Tuple[float, float]:
    if not values:
        return 0.0, 0.0
    m = sum(values) / len(values)
    var = sum((x - m) ** 2 for x in values) / max(len(values) - 1, 1)
    return m, math.sqrt(var)

def detect_anomalies(rows: List[Row]) -> List[Anomaly]:
    """
    Heuristics (works well for a POC):
    1) Large spend vs overall baseline (z-score-ish)
    2) Large spend vs category baseline
    3) New merchant (first time seen in the pulled window)
    4) Duplicate-like charges: same merchant + same amount multiple times
    """
    if not rows:
        return []

    # Treat "spend" as positive magnitude
    amounts = [abs(r[2]) for r in rows]
    overall_mean, overall_std = _mean_std(amounts)

    by_cat = defaultdict(list)
    by_merchant_amount = defaultdict(int)
    seen_merchants = set()

    for d, m, a, c, s in rows:
        by_cat[c].append(abs(a))
        by_merchant_amount[(m.strip().lower(), round(abs(a), 2))] += 1
        seen_merchants.add(m.strip().lower())

    cat_stats = {c: _mean_std(vals) for c, vals in by_cat.items()}

    anomalies: List[Anomaly] = []

    for d, m, a, c, s in rows:
        amt = abs(a)
        m_norm = m.strip().lower()

        # Rule A: extremely large vs overall
        if overall_std > 0 and (amt - overall_mean) / overall_std >= 3.0:
            anomalies.append(Anomaly(d, m, a, c, "Unusually large vs your overall spend pattern", "high"))
            continue

        # Rule B: large vs category baseline
        cat_mean, cat_std = cat_stats.get(c, (0.0, 0.0))
        if cat_std > 0 and (amt - cat_mean) / cat_std >= 3.0:
            anomalies.append(Anomaly(d, m, a, c, f"Unusually large for category '{c}'", "high"))
            continue

        # Rule C: repeated charge pattern (possible duplicate)
        if by_merchant_amount[(m_norm, round(amt, 2))] >= 3:
            anomalies.append(Anomaly(d, m, a, c, "Repeated same amount at same merchant (possible duplicate/recurring)", "medium"))
            continue

    # Optional: “new merchant” signal (low severity)
    # If you want this to be truly “new ever”, we can use db.merchant_exists() per tx later.
    # For now: mark merchants that appear only once in this window.
    merchant_counts = defaultdict(int)
    for _, m, _, _, _ in rows:
        merchant_counts[m.strip().lower()] += 1

    for d, m, a, c, s in rows:
        if merchant_counts[m.strip().lower()] == 1:
            anomalies.append(Anomaly(d, m, a, c, "New/rare merchant in recent period", "low"))

    # sort: high first, then by absolute amount desc
    sev_rank = {"high": 0, "medium": 1, "low": 2}
    anomalies.sort(key=lambda x: (sev_rank.get(x.severity, 9), -abs(x.amount)))

    return anomalies
