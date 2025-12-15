# finance_agent/interfaces/api.py
# FastAPI backend for Finance Agent (Phase 8 MVP)
# - transactions CRUD (basic)
# - anomalies (last N days)
# - statement PDF parse + ingest
# - receipt image OCR parse + ingest (best-effort; graceful fallback)

from __future__ import annotations

import os
import re
import io
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from finance_agent.data.db import FinanceDB
from finance_agent.services.anomaly_detection import detect_anomalies

# Statement parsing (you already built this)
try:
    from finance_agent.tools.pdf_statement import parse_statement_transactions_pdf
except Exception as e:  # pragma: no cover
    parse_statement_transactions_pdf = None  # type: ignore


DB_PATH = os.getenv("FINANCE_DB_PATH", "finance.db")

app = FastAPI(title="Finance Agent API", version="0.2.0")

# Allow local Streamlit dev server(s)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8501", "http://127.0.0.1:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ----------------------------
# Pydantic models
# ----------------------------
class TransactionOut(BaseModel):
    date: str
    merchant: str
    amount: float
    category: str = "Uncategorised"
    source: str = "manual"
    id: Optional[int] = None  # if your DB returns one


class AddTransaction(BaseModel):
    date: str = Field(..., description="YYYY-MM-DD")
    merchant: str
    amount: float
    category: str = "Uncategorised"
    source: str = "manual"


class StatementTx(BaseModel):
    date: str
    merchant: str
    amount: float
    category: str = "Uncategorised"


class ReceiptParseOut(BaseModel):
    date: Optional[str] = None
    merchant: Optional[str] = None
    total_amount: Optional[float] = None
    category: Optional[str] = "Uncategorised"
    raw_text: Optional[str] = None
    warning: Optional[str] = None


class ReceiptIngestIn(BaseModel):
    date: str
    merchant: str
    total_amount: float
    category: str = "Uncategorised"


# ----------------------------
# Helpers
# ----------------------------
def _row_to_tx_dict(row: Any) -> Dict[str, Any]:
    """
    FinanceDB.fetch_transactions might return:
      - tuple: (date, merchant, amount, category, source) OR with id
      - dict
      - object with attributes
    Normalize to a dict for the API response.
    """
    if row is None:
        return {}

    if isinstance(row, dict):
        return row

    if isinstance(row, (list, tuple)):
        # Common shapes
        if len(row) >= 5:
            d = {
                "date": str(row[0]),
                "merchant": str(row[1]),
                "amount": float(row[2]),
                "category": str(row[3]) if row[3] is not None else "Uncategorised",
                "source": str(row[4]) if row[4] is not None else "manual",
            }
            if len(row) >= 6 and row[5] is not None:
                d["id"] = int(row[5])
            return d
        raise ValueError(f"Unexpected transaction tuple length: {len(row)}")

    # Fallback: attribute access
    return {
        "date": str(getattr(row, "date")),
        "merchant": str(getattr(row, "merchant")),
        "amount": float(getattr(row, "amount")),
        "category": str(getattr(row, "category", "Uncategorised") or "Uncategorised"),
        "source": str(getattr(row, "source", "manual") or "manual"),
        "id": getattr(row, "id", None),
    }


def _safe_date_yyyy_mm_dd(value: str) -> str:
    try:
        return datetime.fromisoformat(value).date().isoformat()
    except Exception:
        # accept already in YYYY-MM-DD
        return value


def _ocr_to_text(image_bytes: bytes) -> str:
    """
    Best-effort OCR using pytesseract if available.
    If OCR isn't available on the user's machine, we raise a clear error.
    """
    try:
        from PIL import Image
        import pytesseract
        import io

        img = Image.open(io.BytesIO(image_bytes))
        return pytesseract.image_to_string(img)
    except Exception as e:
        raise RuntimeError(
            "Receipt OCR not available. Install: `uv pip install pillow pytesseract` "
            "and install Tesseract OCR on your OS (Windows: choco install tesseract)."
        ) from e


_money_re = re.compile(r"(?:£\s*)?(\d{1,3}(?:,\d{3})*(?:\.\d{2})|\d+(?:\.\d{2}))")
_date_re = re.compile(
    r"(\d{4}[-/]\d{2}[-/]\d{2})|(\d{2}[-/]\d{2}[-/]\d{4})",
    re.IGNORECASE,
)


def _extract_amount(text: str) -> Optional[float]:
    # Prefer lines containing TOTAL
    candidates: List[float] = []
    for line in text.splitlines():
        if "total" in line.lower():
            for m in _money_re.findall(line):
                try:
                    candidates.append(float(m.replace(",", "")))
                except Exception:
                    pass
    if candidates:
        return max(candidates)

    # Fallback: pick the largest number in the whole text (often total)
    all_nums: List[float] = []
    for m in _money_re.findall(text):
        try:
            all_nums.append(float(m.replace(",", "")))
        except Exception:
            pass
    return max(all_nums) if all_nums else None


def _extract_date(text: str) -> Optional[str]:
    m = _date_re.search(text)
    if not m:
        return None
    raw = m.group(0)
    raw = raw.replace("/", "-")
    # If DD-MM-YYYY, normalize
    parts = raw.split("-")
    if len(parts) == 3 and len(parts[0]) == 2 and len(parts[2]) == 4:
        dd, mm, yyyy = parts
        return f"{yyyy}-{mm}-{dd}"
    return raw


def _extract_merchant(text: str) -> Optional[str]:
    # Heuristic: first non-empty, non-noisy line
    for line in text.splitlines():
        s = re.sub(r"\s+", " ", line).strip()
        if not s:
            continue
        if len(s) < 3:
            continue
        # skip common receipt boilerplate
        if any(k in s.lower() for k in ["vat", "total", "subtotal", "cash", "card", "change"]):
            continue
        # keep it short-ish
        return s[:60]
    return None


# ----------------------------
# Routes
# ----------------------------
@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/transactions", response_model=List[TransactionOut])
def transactions(days: int = 60, category: Optional[str] = None, merchant: Optional[str] = None):
    db = FinanceDB(DB_PATH)
    rows = db.fetch_transactions(days=days, category=category, merchant=merchant)  # type: ignore[arg-type]
    out = []
    for r in rows:
        d = _row_to_tx_dict(r)
        # Defensive defaults
        d["category"] = d.get("category") or "Uncategorised"
        d["source"] = d.get("source") or "manual"
        out.append(d)
    return out


@app.post("/transactions", response_model=Dict[str, Any])
def add_transaction(tx: AddTransaction):
    db = FinanceDB(DB_PATH)
    try:
        db.add_transaction(
            date=_safe_date_yyyy_mm_dd(tx.date),
            merchant=tx.merchant,
            amount=float(tx.amount),
            category=tx.category or "Uncategorised",
            source=tx.source or "manual",
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/anomalies")
def anomalies(days: int = 60):
    db = FinanceDB(DB_PATH)
    rows = db.fetch_transactions(days=days)
    anomalies_ = detect_anomalies(rows)
    return [
        {
            "date": a.date,
            "merchant": a.merchant,
            "amount": a.amount,
            "category": a.category,
            "severity": a.severity,
            "reason": a.reason,
        }
        for a in anomalies_
    ]


@app.post("/statements/parse")
async def parse_statement(file: UploadFile = File(...)):
    if parse_statement_transactions_pdf is None:
        raise HTTPException(status_code=501, detail="Statement parsing tool not available (pdf_statement).")

    data = await file.read()

    # ✅ 1) First try: pass a SEEKABLE stream (fixes "'bytes' object has no attribute 'seek'")
    try:
        bio = io.BytesIO(data)
        bio.seek(0)
        candidates = parse_statement_transactions_pdf(bio)  # type: ignore[misc]
    except Exception:
        # ✅ 2) Fallback: write to a temp file and pass path (most compatible)
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(data)
                tmp.flush()
                tmp_path = tmp.name
            candidates = parse_statement_transactions_pdf(tmp_path)  # type: ignore[misc]
        finally:
            try:
                if "tmp_path" in locals():
                    import os
                    if os.path.exists(tmp_path):
                        os.remove(tmp_path)
            except Exception:
                pass

    # Normalize to plain dicts (keep your existing behaviour)
    out = []
    for c in candidates or []:
        if isinstance(c, dict):
            out.append(c)
        else:
            out.append(
                {
                    "date": getattr(c, "date"),
                    "merchant": getattr(c, "merchant"),
                    "amount": float(getattr(c, "amount")),
                    "category": getattr(c, "category", "Uncategorised") or "Uncategorised",
                }
            )
    return out



# @app.post("/statements/parse")
# async def parse_statement(file: UploadFile = File(...)):
#     if parse_statement_transactions_pdf is None:
#         raise HTTPException(status_code=501, detail="Statement parsing tool not available (pdf_statement).")

#     data = await file.read()
#     # Your parser expects a file path OR bytes depending on your implementation.
#     # We'll try bytes-first, then fallback to temp file.
#     try:
#         candidates = parse_statement_transactions_pdf(data)  # type: ignore[misc]
#     except TypeError:
#         import tempfile
#         with tempfile.NamedTemporaryFile(suffix=".pdf", delete=True) as tmp:
#             tmp.write(data)
#             tmp.flush()
#             candidates = parse_statement_transactions_pdf(tmp.name)  # type: ignore[misc]

#     # Normalize to plain dicts
#     out = []
#     for c in candidates or []:
#         if isinstance(c, dict):
#             out.append(c)
#         else:
#             out.append(
#                 {
#                     "date": getattr(c, "date"),
#                     "merchant": getattr(c, "merchant"),
#                     "amount": float(getattr(c, "amount")),
#                     "category": getattr(c, "category", "Uncategorised") or "Uncategorised",
#                 }
#             )
#     return out


@app.post("/statements/ingest")
def ingest_statements(items: List[StatementTx]):
    db = FinanceDB(DB_PATH)
    added = 0
    for tx in items:
        try:
            db.add_transaction(
                date=_safe_date_yyyy_mm_dd(tx.date),
                merchant=tx.merchant,
                amount=float(tx.amount),
                category=tx.category or "Uncategorised",
                source="statement",
            )
            added += 1
        except Exception:
            # skip duplicates or bad rows
            continue
    return {"added": added}


@app.post("/receipts/parse", response_model=ReceiptParseOut)
async def parse_receipt(file: UploadFile = File(...)):
    data = await file.read()
    try:
        text = _ocr_to_text(data)
    except Exception as e:
        # Keep API explicit so Streamlit can show a clear error
        raise HTTPException(status_code=501, detail=str(e))

    text_clean = text.strip()
    amount = _extract_amount(text_clean)
    date_ = _extract_date(text_clean)
    merch = _extract_merchant(text_clean)

    warning = None
    if amount is None or merch is None:
        warning = "Low confidence parse. Please review and edit before saving."

    return ReceiptParseOut(
        date=date_,
        merchant=merch,
        total_amount=amount,
        category="Uncategorised",
        raw_text=text_clean[:4000] if text_clean else None,
        warning=warning,
    )


@app.post("/receipts/ingest")
def ingest_receipt(payload: ReceiptIngestIn):
    db = FinanceDB(DB_PATH)
    try:
        db.add_transaction(
            date=_safe_date_yyyy_mm_dd(payload.date),
            merchant=payload.merchant,
            amount=float(payload.total_amount),
            category=payload.category or "Uncategorised",
            source="receipt",
        )
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))







# # finance_agent/interfaces/api.py
# # FastAPI backend for Finance Agent
# # - Read/write transactions in finance.db
# # - Serve anomalies
# # - Parse + ingest statement PDFs
# # - Parse + ingest receipt images

# from __future__ import annotations

# import os
# import tempfile
# from datetime import date
# from typing import List, Optional

# from fastapi import FastAPI, HTTPException, UploadFile, File
# from fastapi.middleware.cors import CORSMiddleware
# from pydantic import BaseModel, Field
# from dotenv import load_dotenv

# from finance_agent.data.db import FinanceDB
# from finance_agent.services.anomaly_detection import detect_anomalies
# from finance_agent.tools.pdf_statement import parse_statement_transactions_pdf

# # Optional receipt pipeline (only enabled if you have these modules)
# try:
#     from finance_agent.tools.receipt_ocr import extract_text_from_receipt
#     from finance_agent.tools.receipt_parser import parse_receipt_text
#     _RECEIPT_ENABLED = True
# except Exception:
#     _RECEIPT_ENABLED = False


# # Load environment variables (OPENAI_API_KEY etc.)
# load_dotenv()

# app = FastAPI(title="Finance Agent API", version="0.2.0")

# # Allow Streamlit (localhost) to call the API
# app.add_middleware(
#     CORSMiddleware,
#     allow_origins=["http://localhost", "http://127.0.0.1", "http://localhost:8501", "http://127.0.0.1:8501"],
#     allow_credentials=True,
#     allow_methods=["*"],
#     allow_headers=["*"],
# )

# DB_PATH = os.getenv("FINANCE_DB_PATH", "finance.db")


# # -----------------------------
# # Models
# # -----------------------------
# class TransactionIn(BaseModel):
#     date: str = Field(..., description="YYYY-MM-DD")
#     merchant: str
#     amount: float
#     category: str = "Uncategorised"
#     source: str = "manual"


# class TransactionOut(TransactionIn):
#     id: Optional[int] = None


# class StatementTxIn(BaseModel):
#     date: str  # YYYY-MM-DD
#     merchant: str
#     amount: float
#     direction: str  # "in" | "out"
#     currency: str = "GBP"
#     category: Optional[str] = None


# class ReceiptParsed(BaseModel):
#     date: str
#     merchant: str
#     total_amount: float
#     category: str


# # -----------------------------
# # Health
# # -----------------------------
# @app.get("/health")
# def health():
#     return {"ok": True}


# @app.get(
#     "/transactions",
#     response_model=list[TransactionOut],
#     summary="Get transactions",
#     description="Fetch transactions from the ledger database.",
# )
# def get_transactions(days: int = 60, category: Optional[str] = None, merchant: Optional[str] = None):
#     db = FinanceDB(DB_PATH)
#     rows = db.fetch_transactions(days=days, category=category, merchant=merchant)

#     out: list[dict] = []
#     for r in rows:
#         # Case 1: DB returns a tuple row
#         if isinstance(r, tuple) or isinstance(r, list):
#             # expected: (date, merchant, amount, category, source)
#             d, m, a, c, s = (list(r) + [None] * 5)[:5]
#             out.append({
#                 "date": str(d),
#                 "merchant": m,
#                 "amount": float(a),
#                 "category": c or "Uncategorised",
#                 "source": s or "manual",
#             })
#         else:
#             # Case 2: DB returns an object with attributes
#             out.append({
#                 "date": str(getattr(r, "date", "")),
#                 "merchant": getattr(r, "merchant", ""),
#                 "amount": float(getattr(r, "amount", 0.0)),
#                 "category": getattr(r, "category", "Uncategorised") or "Uncategorised",
#                 "source": getattr(r, "source", "manual") or "manual",
#             })

#     return out


# @app.post("/transactions")
# def add_transaction(tx: TransactionIn):
#     try:
#         db = FinanceDB(DB_PATH)
#         try:
#             db.add_transaction(
#                 date=tx.date,
#                 merchant=tx.merchant,
#                 amount=float(tx.amount),
#                 category=tx.category,
#                 source=tx.source,
#             )
#         except TypeError:
#             # Backwards-compatible DBs may not support a `source` column yet
#             db.add_transaction(tx.date, tx.merchant, float(tx.amount), tx.category)            
#         return {"ok": True}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # -----------------------------
# # Anomalies
# # -----------------------------
# @app.get("/anomalies")
# def anomalies(days: int = 60):
#     try:
#         db = FinanceDB(DB_PATH)
#         rows = db.fetch_transactions(days=days)
#         anomalies = detect_anomalies(rows)
#         return [
#             {
#                 "date": a.date,
#                 "merchant": a.merchant,
#                 "amount": a.amount,
#                 "category": a.category,
#                 "severity": a.severity,
#                 "reason": a.reason,
#             }
#             for a in anomalies
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # -----------------------------
# # Statement PDF parsing + ingestion
# # -----------------------------
# @app.post("/statements/parse")
# async def parse_statement(file: UploadFile = File(...)):
#     """
#     Upload a PDF bank statement and return candidate transactions.
#     (No DB writes here; the UI can confirm selection.)
#     """
#     if not file.filename.lower().endswith(".pdf"):
#         raise HTTPException(status_code=400, detail="Please upload a .pdf file")

#     try:
#         with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
#             tmp.write(await file.read())
#             tmp_path = tmp.name

#         txs = parse_statement_transactions_pdf(tmp_path)
#         return [
#             {
#                 "date": t.date,
#                 "merchant": t.merchant,
#                 "amount": t.amount,
#                 "direction": t.direction,
#                 "currency": getattr(t, "currency", "GBP"),
#             }
#             for t in txs
#         ]
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         try:
#             if "tmp_path" in locals() and os.path.exists(tmp_path):
#                 os.remove(tmp_path)
#         except Exception:
#             pass


# @app.post("/statements/ingest")
# def ingest_statement(selected: List[StatementTxIn]):
#     """
#     Ingest already-parsed statement transactions into finance.db.
#     """
#     if not selected:
#         return {"ok": True, "added": 0}

#     try:
#         db = FinanceDB(DB_PATH)
#         for t in selected:
#             category = t.category or "Uncategorised"
#             db.add_transaction(
#                 date=t.date,
#                 merchant=t.merchant,
#                 amount=float(t.amount),
#                 category=category,
#                 source="statement",
#             )
#         return {"ok": True, "added": len(selected)}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))


# # -----------------------------
# # Receipt parsing + ingestion
# # -----------------------------
# @app.post("/receipts/parse")
# async def parse_receipt(file: UploadFile = File(...)):
#     """
#     Upload a receipt image, OCR it, then use LLM to extract structured fields.
#     """
#     if not _RECEIPT_ENABLED:
#         raise HTTPException(status_code=501, detail="Receipt tools not enabled in this environment")

#     try:
#         suffix = os.path.splitext(file.filename)[1].lower() or ".png"
#         with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
#             tmp.write(await file.read())
#             tmp_path = tmp.name

#         raw_text = extract_text_from_receipt(tmp_path)
#         parsed = parse_receipt_text(raw_text)  # expected dict-like
#         # normalise keys
#         return {
#             "date": parsed.get("date"),
#             "merchant": parsed.get("merchant"),
#             "total_amount": float(parsed.get("total_amount")),
#             "category": parsed.get("category", "Uncategorised"),
#             "raw_text": raw_text[:2000],
#         }
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
#     finally:
#         try:
#             if "tmp_path" in locals() and os.path.exists(tmp_path):
#                 os.remove(tmp_path)
#         except Exception:
#             pass


# @app.post("/receipts/ingest")
# def ingest_receipt(data: ReceiptParsed):
#     if not _RECEIPT_ENABLED:
#         raise HTTPException(status_code=501, detail="Receipt tools not enabled in this environment")

#     try:
#         db = FinanceDB(DB_PATH)
#         db.add_transaction(
#             date=data.date,
#             merchant=data.merchant,
#             amount=float(data.total_amount),
#             category=data.category,
#             source="receipt",
#         )
#         return {"ok": True}
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=str(e))
