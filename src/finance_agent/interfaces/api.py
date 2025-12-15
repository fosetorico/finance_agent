from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os

from finance_agent.data.db import FinanceDB
from finance_agent.services.anomaly_detection import detect_anomalies

app = FastAPI(title="Finance Agent API", version="0.1.0")

DB_PATH = os.getenv("FINANCE_DB_PATH", "finance.db")


class AddTransaction(BaseModel):
    date: str
    merchant: str
    amount: float
    category: str = "Uncategorised"
    source: str = "manual"


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/transactions")
def get_transactions(days: int = 60, category: Optional[str] = None, merchant: Optional[str] = None):
    db = FinanceDB(DB_PATH)
    rows = db.fetch_transactions(days=days, category=category, merchant=merchant)
    # rows: (date, merchant, amount, category, source)
    return [
        {"date": d, "merchant": m, "amount": a, "category": c, "source": s}
        for (d, m, a, c, s) in rows
    ]


@app.post("/transactions")
def add_transaction(tx: AddTransaction):
    db = FinanceDB(DB_PATH)
    try:
        db.add_transaction(
            date=tx.date,
            merchant=tx.merchant,
            amount=float(tx.amount),
            category=tx.category,
            source=tx.source,
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/anomalies")
def anomalies(days: int = 60):
    db = FinanceDB(DB_PATH)
    rows = db.fetch_transactions(days=days)
    anomalies = detect_anomalies(rows)
    return [
        {
            "date": a.date,
            "merchant": a.merchant,
            "amount": a.amount,
            "category": a.category,
            "severity": a.severity,
            "reason": a.reason,
        }
        for a in anomalies
    ]
