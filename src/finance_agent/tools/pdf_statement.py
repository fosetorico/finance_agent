"""finance_agent.tools.pdf_statement

LLM-assisted PDF parsing for bank statement PDFs.

What this module does
- Reads text from a PDF statement using pdfplumber.
- Attempts a rule-based transaction parse (fast + cheap).
- If rule-based parsing yields no/too-few results, falls back to an OpenAI LLM
  to parse ONLY the candidate transaction lines.

This design keeps the system robust without forcing you to rely on perfect PDF text.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
import os
import re
from typing import Iterable, List, Optional, Tuple

import pdfplumber

# Load .env if present (so OPENAI_API_KEY works when running via uv)
try:
    from dotenv import load_dotenv

    # Load environment variables from .env (root of project)
    load_dotenv()
except Exception:
    # dotenv is optional; if not installed, env vars must be provided by the shell
    pass

# Create OpenAI client (only used in LLM fallback)
try:
    from openai import OpenAI

    _openai_client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
except Exception:
    _openai_client = None


@dataclass
class StatementTx:
    """A normalised transaction extracted from a PDF statement."""

    date: str  # YYYY-MM-DD
    merchant: str
    amount: float
    direction: str  # "in" | "out"
    currency: str = "GBP"
    category: str = "Uncategorised"


# --- Utilities --------------------------------------------------------------
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

# --- Merchant cleanup --------------------------------------------------------
_NOISE_TOKENS = [
    "DESCRIPTION", "TYPE", "MONEY", "IN", "OUT", "BALANCE", "COLUMN",
    "DATE", "CDOLumn", "CTolumn", "DFescription", "DLescription",
    "DSescription", "DAescription", "DWescription",
    "Moneyb", "Ilna", "n(k£.)", "TFype", "TCype", "TDype", "DW", "DA", "DS"
]


def _clean_merchant(raw: str) -> str:
    """Remove PDF column-noise and leave a short merchant string."""
    if not raw:
        return "UNKNOWN"

    s = raw

    # Remove common column words / artefacts (case-insensitive)
    for tok in _NOISE_TOKENS:
        s = re.sub(rf"\b{re.escape(tok)}\b", " ", s, flags=re.IGNORECASE)

    # Remove tiny type codes like PO / PT / EB / PI (often not useful for merchant)
    s = re.sub(r"\b[A-Z]{2}\b", " ", s)

    # Remove leftover punctuation & collapse whitespace
    s = re.sub(r"[|:;]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip(" -")

    # Keep it short-ish (helps categoriser)
    if len(s) > 60:
        s = s[:60].strip()

    return s or "UNKNOWN"


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract raw text from a PDF using pdfplumber."""

    chunks: List[str] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            txt = page.extract_text() or ""
            if txt:
                chunks.append(txt)
    return "\n".join(chunks)


def _normalise_pdf_text(text: str) -> str:
    """Clean up common PDF extraction artifacts (not OCR, but similar noise)."""

    # Fix common Lloyds extraction artefacts seen in your sample (D0ate, DFescription, etc.)
    text = re.sub(r"\bD0ate\b", "Date", text)
    text = re.sub(r"\bDFescription\b", "Description", text)
    text = re.sub(r"\bDSescription\b", "Description", text)
    text = re.sub(r"\bDAescription\b", "Description", text)
    text = re.sub(r"\bDWescription\b", "Description", text)
    text = re.sub(r"\bCTolumn\b", "Column", text)

    # Collapse repeated spaces and weird dots separators
    text = re.sub(r"[·•]+", " ", text)
    text = re.sub(r"\s+", " ", text)

    # Restore line breaks around 'Date <d> <Mon> <yy>' patterns so we can split lines reliably
    text = re.sub(r"(Date\s+\d{1,2}\s+[A-Za-z]{3}\s+\d{2})", r"\n\1", text)
    return text.strip()


def _parse_statement_period(text: str) -> Tuple[Optional[date], Optional[date]]:
    """Try to detect the statement period (start/end). Helps interpret 2-digit years."""

    # Example in your PDF: "01 November 2025 to 23 November 2025"
    m = re.search(
        r"(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+to\s+(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})",
        text,
        flags=re.IGNORECASE,
    )
    if not m:
        return None, None

    d1, mon1, y1, d2, mon2, y2 = m.groups()
    start = date(int(y1), _MONTHS[mon1[:3].lower()], int(d1))
    end = date(int(y2), _MONTHS[mon2[:3].lower()], int(d2))
    return start, end


def _candidate_transaction_lines(text: str) -> List[str]:
    """Return likely transaction lines from noisy statement text."""

    # Looks like: "Date 3 Nov 25 Description ... 600.00 ... 708.51"
    date_pat = re.compile(r"\bDate\s+(\d{1,2})\s+([A-Za-z]{3})\s+(\d{2,4})\b")

    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    candidates: List[str] = []

    for ln in lines:
        if date_pat.search(ln):
            # Remove obvious header garbage if present
            if "Your Transactions" in ln or "Column" in ln:
                continue
            candidates.append(ln)

    # De-duplicate while preserving order
    seen = set()
    out: List[str] = []
    for ln in candidates:
        if ln not in seen:
            out.append(ln)
            seen.add(ln)
    return out


def _try_rule_based(lines: Iterable[str], default_year: Optional[int]) -> List[StatementTx]:
    """Cheap heuristic parser.

    Works for clean lines.
    If the PDF text is noisy (common), this may return 0 and we fall back to LLM.
    """

    txs: List[StatementTx] = []

    date_pat = re.compile(r"\bDate\s+(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+(?P<yr>\d{2,4})\b")
    money_pat = re.compile(r"(-?\d[\d,]*\.\d{2})")

    for ln in lines:
        dm = date_pat.search(ln)
        if not dm:
            continue

        day = int(dm.group("day"))
        mon = _MONTHS.get(dm.group("mon").lower())
        if not mon:
            continue

        yr_raw = dm.group("yr")
        yr = int(yr_raw)
        if yr < 100:
            yr = (default_year // 100) * 100 + yr if default_year else 2000 + yr

        # Pull out money numbers; on your Lloyds sample, line tends to have [amount, balance]
        nums = [float(x.replace(",", "")) for x in money_pat.findall(ln)]
        if not nums:
            continue

        amount = nums[0]

        # Guess direction (very rough): if tokens include "Money In" and not "Money Out"
        direction = "out"
        if re.search(r"\bMoney\s*In\b", ln, flags=re.IGNORECASE) and not re.search(
            r"\bMoney\s*Out\b", ln, flags=re.IGNORECASE
        ):
            direction = "in"

        # Merchant: take the text between the date and the first money number
        after_date = ln[dm.end() :]
        # Remove common column labels / type codes
        after_date = re.sub(r"\bDescription\b", " ", after_date, flags=re.IGNORECASE)
        after_date = re.sub(r"\bType\b\s+[A-Z]{2}\b", " ", after_date)
        # Stop at the first amount occurrence
        first_money_idx = after_date.find(f"{nums[0]:.2f}")
        # merchant = after_date[: first_money_idx if first_money_idx != -1 else 80].strip(" -|:;")
        # merchant = re.sub(r"\s+", " ", merchant).strip()
        merchant_raw = after_date[: first_money_idx if first_money_idx != -1 else 80]
        merchant = _clean_merchant(merchant_raw)

        if not merchant:
            merchant = "UNKNOWN"

        dt = date(yr, mon, day).isoformat()
        txs.append(StatementTx(date=dt, merchant=merchant, amount=abs(amount), direction=direction))

    return txs


def _safe_json_extract(text: str) -> Optional[object]:
    """Extract a JSON object/array from an LLM response safely."""

    if not text:
        return None

    # Strip code fences if present
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"```$", "", text).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except Exception:
        pass

    # Try to locate first JSON array/object
    m = re.search(r"(\[.*\]|\{.*\})", text, flags=re.DOTALL)
    if not m:
        return None

    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def _llm_parse_transactions(lines: List[str], period: Tuple[Optional[date], Optional[date]]) -> List[StatementTx]:
    """Use an OpenAI model to parse transaction lines into structured rows."""

    if _openai_client is None:
        raise RuntimeError(
            "OpenAI client not available. Install openai and set OPENAI_API_KEY in your environment."
        )

    start, end = period
    period_hint = ""
    if start and end:
        period_hint = f"Statement period: {start.isoformat()} to {end.isoformat()}. "

    # Keep the prompt tight; pass only the candidate lines.
    payload = "\n".join(f"- {ln}" for ln in lines[:200])

    prompt = (
        "You are extracting transactions from a bank statement. "
        + period_hint
        + "Each bullet is ONE transaction line extracted from a PDF. "
        "Return ONLY valid JSON (no commentary), as an array of objects with keys: "
        "date (YYYY-MM-DD), merchant, amount (number), direction ('in' or 'out'), currency ('GBP'). "
        "Rules:\n"
        "- Interpret dates like '3 Nov 25' using the statement period year if needed.\n"
        "- 'amount' should be a positive number (absolute value).\n"
        "- If the line shows a credit/incoming payment, direction='in', else 'out'.\n"
        "- Ignore balances.\n"
        "- Merchant should be a short cleaned description (no column labels).\n\n"
        "Transaction lines:\n"
        + payload
    )

    # Use a cost-effective model; you can swap to a stronger one if needed.
    resp = _openai_client.responses.create(
        model=os.getenv("OPENAI_STATEMENT_MODEL", "gpt-4.1-mini"),
        input=prompt,
    )

    # The python SDK returns output chunks; best-effort join.
    out_text = ""
    try:
        out_text = resp.output_text
    except Exception:
        # Fallback if SDK shape differs
        out_text = str(resp)

    parsed = _safe_json_extract(out_text)
    if not parsed or not isinstance(parsed, list):
        raise ValueError("LLM did not return a JSON array of transactions")

    txs: List[StatementTx] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue

        dt = str(item.get("date", "")).strip()
        merchant = str(item.get("merchant", "")).strip() or "UNKNOWN"
        currency = str(item.get("currency", "GBP")).strip() or "GBP"
        direction = str(item.get("direction", "out")).strip().lower()

        try:
            amount = float(item.get("amount"))
        except Exception:
            continue

        if direction not in {"in", "out"}:
            direction = "out"

        txs.append(
            StatementTx(
                date=dt,
                merchant=merchant,
                amount=abs(amount),
                direction=direction,
                currency=currency,
            )
        )

    return txs


# --- Public API -------------------------------------------------------------
def parse_statement_transactions_pdf(pdf_path: str) -> List[StatementTx]:
    """Main entrypoint used by the CLI/ingestion service."""

    raw = extract_text_from_pdf(pdf_path)
    if not raw.strip():
        return []

    norm = _normalise_pdf_text(raw)
    period = _parse_statement_period(raw)
    default_year = period[0].year if period[0] else None

    lines = _candidate_transaction_lines(norm)
    if not lines:
        # If we can't even find candidate lines, try LLM on the whole normalised text
        # (still bounded - but can be more expensive)
        lines = [norm[:8000]]

    # 1) Cheap heuristic attempt
    txs = _try_rule_based(lines, default_year=default_year)

    # 2) LLM fallback when rule-based fails / yields too few
    if len(txs) < 3:
        txs = _llm_parse_transactions(lines, period=period)

    return txs
