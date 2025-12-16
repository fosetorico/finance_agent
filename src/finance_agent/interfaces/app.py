# src/finance_agent/interfaces/app.py
# Streamlit UI for Finance Agent (Phase 8 + Phase 9 chat)
# - Dashboard: filters + charts + tables
# - Uploads: statement PDF + receipt image
# - Add Transaction: manual form
# - Chat: finance-only assistant that can query API + propose DB writes with confirm

from __future__ import annotations

from datetime import date, datetime, timedelta
import re
import uuid

import pandas as pd
import requests
import streamlit as st


# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="Finance Agent", layout="wide")
st.title("💷 Finance Agent")

# -----------------------------
# Backend config
# -----------------------------
API_BASE = "http://127.0.0.1:8000"  # FastAPI base URL


def api_get(path: str, params: dict | None = None, timeout: int = 30):
    url = f"{API_BASE}{path}"
    resp = requests.get(url, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def api_post_json(path: str, payload: dict, timeout: int = 60):
    url = f"{API_BASE}{path}"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


def api_post_file(path: str, file_bytes: bytes, filename: str, mime: str, timeout: int = 180):
    url = f"{API_BASE}{path}"
    files = {"file": (filename, file_bytes, mime)}
    resp = requests.post(url, files=files, timeout=timeout)
    resp.raise_for_status()
    return resp.json()


# -----------------------------
# Data loaders
# -----------------------------
@st.cache_data(ttl=15, show_spinner=False)
def load_transactions(days: int) -> pd.DataFrame:
    data = api_get("/transactions", params={"days": days})
    df = pd.DataFrame(data)
    if df.empty:
        return df

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    if "category" in df.columns:
        df["category"] = df["category"].fillna("Uncategorised")
    if "merchant" in df.columns:
        df["merchant"] = df["merchant"].fillna("Unknown")
    if "source" in df.columns:
        df["source"] = df["source"].fillna("unknown")

    df = df.sort_values("date", ascending=False, na_position="last")
    return df


@st.cache_data(ttl=15, show_spinner=False)
def load_anomalies(days: int) -> pd.DataFrame:
    data = api_get("/anomalies", params={"days": days})
    df = pd.DataFrame(data)
    if df.empty:
        return df

    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    if "category" in df.columns:
        df["category"] = df["category"].fillna("Uncategorised")
    if "merchant" in df.columns:
        df["merchant"] = df["merchant"].fillna("Unknown")
    if "severity" in df.columns:
        df["severity"] = df["severity"].fillna("unknown")

    df = df.sort_values("date", ascending=False, na_position="last")
    return df


# -----------------------------
# Sidebar controls (Phase 8 style kept)
# -----------------------------
st.sidebar.header("Controls")

days = st.sidebar.number_input("Lookback days (API)", min_value=7, max_value=365, value=60, step=1)
refresh = st.sidebar.button("🔄 Refresh")

if refresh:
    # Clear cached API calls
    st.cache_data.clear()

with st.spinner("Loading data..."):
    df_tx = load_transactions(days)
    df_an = load_anomalies(days)

# Date range filter (based on transactions)
if not df_tx.empty and "date" in df_tx.columns:
    tx_min = df_tx["date"].min().date() if pd.notna(df_tx["date"].min()) else None
    tx_max = df_tx["date"].max().date() if pd.notna(df_tx["date"].max()) else None
else:
    tx_min, tx_max = None, None

if tx_min and tx_max:
    default_start, default_end = tx_min, tx_max
elif tx_max:
    default_start, default_end = tx_max, tx_max
else:
    default_start = default_end = pd.Timestamp.today().date()

date_range = st.sidebar.date_input("Date range (within lookback)", value=(default_start, default_end))

# Category filter
cat_options = ["All"]
if not df_tx.empty and "category" in df_tx.columns:
    cat_options += sorted([c for c in df_tx["category"].dropna().unique().tolist()])

selected_category = st.sidebar.selectbox("Category", cat_options)

# Merchant search
merchant_q = st.sidebar.text_input("Search merchant", placeholder="e.g. Tesco, Uber, PAY")

# Optional severity filter (only shows if anomalies exist)
severity_filter = None
if not df_an.empty and "severity" in df_an.columns:
    severities = sorted(df_an["severity"].dropna().unique().tolist())
    if severities:
        severity_filter = st.sidebar.multiselect("Anomaly severity", severities, default=severities)

# Apply filters to transactions
df_tx_f = df_tx.copy()
if not df_tx_f.empty and "date" in df_tx_f.columns:
    start_d, end_d = date_range
    df_tx_f = df_tx_f[(df_tx_f["date"].dt.date >= start_d) & (df_tx_f["date"].dt.date <= end_d)]

if selected_category != "All" and "category" in df_tx_f.columns:
    df_tx_f = df_tx_f[df_tx_f["category"] == selected_category]

if merchant_q and "merchant" in df_tx_f.columns:
    df_tx_f = df_tx_f[df_tx_f["merchant"].str.contains(merchant_q, case=False, na=False)]

# Apply similar filters to anomalies
df_an_f = df_an.copy()
if not df_an_f.empty and "date" in df_an_f.columns:
    start_d, end_d = date_range
    df_an_f = df_an_f[(df_an_f["date"].dt.date >= start_d) & (df_an_f["date"].dt.date <= end_d)]

if selected_category != "All" and "category" in df_an_f.columns:
    df_an_f = df_an_f[df_an_f["category"] == selected_category]

if merchant_q and "merchant" in df_an_f.columns:
    df_an_f = df_an_f[df_an_f["merchant"].str.contains(merchant_q, case=False, na=False)]

if severity_filter is not None and not df_an_f.empty and "severity" in df_an_f.columns:
    if severity_filter:
        df_an_f = df_an_f[df_an_f["severity"].isin(severity_filter)]


# -----------------------------
# Tabs (Phase 8 + Phase 9 chat)
# -----------------------------
tab_dash, tab_uploads, tab_add, tab_chat = st.tabs(["📊 Dashboard", "📤 Uploads", "➕ Add Transaction", "💬 Chat"])


# -----------------------------
# Dashboard tab (kept aligned to Phase 8.1.2)
# -----------------------------
with tab_dash:
    # Metrics
    colm1, colm2, colm3, colm4 = st.columns(4)
    tx_count = int(df_tx_f.shape[0]) if not df_tx_f.empty else 0
    an_count = int(df_an_f.shape[0]) if not df_an_f.empty else 0
    total_spend = float(df_tx_f["amount"].sum()) if (not df_tx_f.empty and "amount" in df_tx_f.columns) else 0.0
    unique_merchants = int(df_tx_f["merchant"].nunique()) if (not df_tx_f.empty and "merchant" in df_tx_f.columns) else 0
    colm1.metric("Transactions", tx_count)
    colm2.metric("Anomalies", an_count)
    colm3.metric("Total amount (filtered)", f"£{total_spend:,.2f}")
    colm4.metric("Unique merchants", unique_merchants)

    st.divider()

    # Charts
    st.subheader("📈 Insights")

    if df_tx_f.empty:
        st.info("No transactions found for the selected window/filters.")
    else:
        c1, c2 = st.columns(2)

        with c1:
            st.caption("Spend by category")
            if "category" in df_tx_f.columns and "amount" in df_tx_f.columns:
                by_cat = (
                    df_tx_f.dropna(subset=["category", "amount"])
                          .groupby("category", as_index=True)["amount"]
                          .sum()
                          .sort_values(ascending=False)
                )
                st.bar_chart(by_cat, height=280)
            else:
                st.warning("Missing 'category' or 'amount' fields in transactions.")

        with c2:
            st.caption("Spend over time")
            if "date" in df_tx_f.columns and "amount" in df_tx_f.columns:
                by_day = (
                    df_tx_f.dropna(subset=["date", "amount"])
                          .groupby(df_tx_f["date"].dt.date, as_index=True)["amount"]
                          .sum()
                          .sort_index()
                )
                st.line_chart(by_day, height=280)
            else:
                st.warning("Missing 'date' or 'amount' fields in transactions.")

        c3, c4 = st.columns(2)

        with c3:
            st.caption("Top merchants (by total amount)")
            if "merchant" in df_tx_f.columns and "amount" in df_tx_f.columns:
                top_merchants = (
                    df_tx_f.dropna(subset=["merchant", "amount"])
                          .groupby("merchant", as_index=True)["amount"]
                          .sum()
                          .sort_values(ascending=False)
                          .head(10)
                )
                st.bar_chart(top_merchants, height=280)
            else:
                st.warning("Missing 'merchant' or 'amount' fields in transactions.")

        with c4:
            st.caption("Anomaly counts")
            if df_an_f.empty:
                st.info("No anomalies detected in this window.")
            else:
                if "severity" in df_an_f.columns:
                    counts = df_an_f["severity"].value_counts()
                    st.bar_chart(counts, height=280)
                else:
                    st.bar_chart(pd.Series({"anomalies": len(df_an_f)}), height=280)

    st.divider()

    # Tables
    colA, colB = st.columns(2)

    with colA:
        st.subheader("📒 Transactions")
        if df_tx_f.empty:
            st.info("No transactions yet.")
        else:
            show_cols = [c for c in ["date", "merchant", "amount", "category", "source"] if c in df_tx_f.columns]
            st.dataframe(df_tx_f[show_cols], width="stretch", hide_index=True)

    with colB:
        st.subheader("⚠️ Anomalies")
        if df_an_f.empty:
            st.info("No anomalies yet.")
        else:
            show_cols = [c for c in ["date", "merchant", "amount", "category", "severity", "reason"] if c in df_an_f.columns]
            st.dataframe(df_an_f[show_cols], width="stretch", hide_index=True)


# -----------------------------
# Uploads tab (Phase 8.1.3)
# -----------------------------
with tab_uploads:
    st.subheader("Upload bank statement PDF")

    if "statement_candidates" not in st.session_state:
        st.session_state["statement_candidates"] = None

    pdf = st.file_uploader("Choose a PDF statement", type=["pdf"], key="pdf_upload")
    if pdf is not None and st.button("Parse statement", key="btn_parse_stmt"):
        try:
            cand = api_post_file("/statements/parse", pdf.getvalue(), pdf.name, "application/pdf")
            st.session_state["statement_candidates"] = cand
            st.success(f"Found {len(cand)} candidate transactions.")
        except Exception as e:
            st.error(f"Statement parse failed: {e}")

    cand = st.session_state.get("statement_candidates")
    if cand:
        df_c = pd.DataFrame(cand)
        st.dataframe(df_c, width="stretch", hide_index=True)

        st.write("Select which ones to ingest:")
        selected_idx = st.multiselect(
            "Transactions",
            options=list(range(len(cand))),
            default=list(range(len(cand))),
            format_func=lambda i: f"{cand[i].get('date')} | {cand[i].get('merchant')} | £{cand[i].get('amount')}",
            key="stmt_select",
        )
        if st.button("Ingest selected", key="btn_ingest_stmt"):
            try:
                payload = [cand[i] for i in selected_idx]
                res = api_post_json("/statements/ingest", payload)
                st.success(f"Added {res.get('added', 0)} transactions to finance.db")
                st.session_state["statement_candidates"] = None
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Ingest failed: {e}")

    st.divider()
    st.subheader("Upload receipt image")

    if "receipt_parsed" not in st.session_state:
        st.session_state["receipt_parsed"] = None

    img = st.file_uploader("Choose a receipt image", type=["png", "jpg", "jpeg"], key="receipt_upload")
    if img is not None and st.button("Parse receipt", key="btn_parse_receipt"):
        try:
            parsed = api_post_file("/receipts/parse", img.getvalue(), img.name, img.type or "image/png")
            st.session_state["receipt_parsed"] = parsed
            st.success("Receipt parsed. Review and save below.")
        except Exception as e:
            st.error(f"Receipt parse failed: {e}")

    parsed = st.session_state.get("receipt_parsed")
    if parsed:
        st.write("Review / edit fields before saving:")
        col1, col2 = st.columns(2)
        with col1:
            r_date = st.text_input("Date (YYYY-MM-DD)", value=str(parsed.get("date") or ""))
            r_merchant = st.text_input("Merchant", value=str(parsed.get("merchant") or ""))
        with col2:
            r_amount = st.number_input("Total amount", value=float(parsed.get("total_amount") or 0.0))
            r_category = st.text_input("Category", value=str(parsed.get("category") or "Uncategorised"))

        if st.button("Save receipt as transaction", key="btn_save_receipt"):
            try:
                api_post_json("/receipts/ingest", {
                    "date": r_date,
                    "merchant": r_merchant,
                    "total_amount": float(r_amount),
                    "category": r_category,
                })
                st.success("Receipt saved to finance.db")
                st.session_state["receipt_parsed"] = None
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Save failed: {e}")


# -----------------------------
# Add Transaction tab (Phase 8)
# -----------------------------
with tab_add:
    st.subheader("Add transaction (manual)")

    with st.form("add_tx_form"):
        c1, c2 = st.columns(2)
        with c1:
            f_date = st.date_input("Date").strftime("%Y-%m-%d")
            f_merchant = st.text_input("Merchant")
        with c2:
            f_amount = st.number_input("Amount", value=0.0)
            f_category = st.text_input("Category", value="Uncategorised")
        f_source = st.selectbox("Source", ["manual", "receipt", "statement", "import"])
        submitted = st.form_submit_button("Add transaction")

    if submitted:
        try:
            api_post_json("/transactions", {
                "date": f_date,
                "merchant": f_merchant,
                "amount": float(f_amount),
                "category": f_category,
                "source": f_source,
            })
            st.success("Transaction added.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Add failed: {e}")


# -----------------------------
# Phase 9 — Chat tab
# -----------------------------
with tab_chat:
    st.subheader("💬 Chat (finance-only)")
    st.caption("Ask about transactions/anomalies or draft an add-transaction command. You'll confirm before saving.")

    # Session identity for stateful chat
    if "chat_session_id" not in st.session_state:
        st.session_state["chat_session_id"] = str(uuid.uuid4())

    # Chat message format:
    # {"role": "user"/"assistant", "type": "text"/"table", "content": "...", "title": "...", "rows": [...]}
    if "chat_messages" not in st.session_state:
        st.session_state["chat_messages"] = []

    if "pending_tx" not in st.session_state:
        st.session_state["pending_tx"] = None

    def add_text(role: str, content: str):
        st.session_state["chat_messages"].append({"role": role, "type": "text", "content": content})

    def add_table(title: str, rows: list[dict]):
        st.session_state["chat_messages"].append({
            "role": "assistant",
            "type": "table",
            "title": title,
            "rows": rows,
        })

    # Render chat history (text + tables)
    for m in st.session_state["chat_messages"]:
        with st.chat_message(m["role"]):
            if m.get("type") == "table":
                st.markdown(f"**{m.get('title','Results')}**")
                df = pd.DataFrame(m.get("rows") or [])
                if df.empty:
                    st.info("No rows to display.")
                else:
                    # keep nice column ordering if present
                    preferred = ["date", "merchant", "amount", "category", "source", "severity", "reason"]
                    show_cols = [c for c in preferred if c in df.columns]
                    st.dataframe(df[show_cols] if show_cols else df, width="stretch", hide_index=True)
            else:
                st.write(m.get("content", ""))

    # Helper: minimal intent parsing (no keywords required, within reason)
    MONEY_RE = re.compile(r"(?:£\s*)?(\d+(?:\.\d{1,2})?)")
    DATE_ISO_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
    DATE_UK_RE = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{2,4})\b")

    def parse_days(text: str, default: int = 60) -> int:
        m = re.search(r"\b(last|past)\s+(\d{1,3})\s+days?\b", text.lower())
        if m:
            try:
                return max(1, min(365, int(m.group(2))))
            except Exception:
                return default
        return default

    def parse_date(text: str) -> date | None:
        t = text.lower()
        if "today" in t:
            return date.today()
        if "yesterday" in t:
            return date.today() - timedelta(days=1)
        m = DATE_ISO_RE.search(text)
        if m:
            y, mo, d = map(int, m.groups())
            return date(y, mo, d)
        m = DATE_UK_RE.search(text)
        if m:
            d, mo, y = m.groups()
            y = int(y)
            if y < 100:
                y += 2000
            return date(y, int(mo), int(d))
        return None

    def parse_amount(text: str) -> float | None:
        m = MONEY_RE.search(text.replace(",", ""))
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def guess_merchant(text: str) -> str:
        cleaned = MONEY_RE.sub(" ", text)
        cleaned = DATE_ISO_RE.sub(" ", cleaned)
        cleaned = DATE_UK_RE.sub(" ", cleaned)
        stop = {"add","spent","spend","paid","pay","purchase","bought","on","at","to","for","today","yesterday","my","a","an","the"}
        tokens = [t.strip(" ,.-") for t in cleaned.split() if t.strip(" ,.-")]
        tokens = [t for t in tokens if t.lower() not in stop]
        return (" ".join(tokens).strip() or "Unknown")[:80]

    def is_add_intent(text: str) -> bool:
        t = text.lower()
        if MONEY_RE.search(t) and any(k in t for k in ["add","spent","paid","bought","purchase","uber","tesco","aldi","sainsbury"]):
            return True
        if MONEY_RE.search(t) and len(t.split()) >= 2 and ("today" in t or "yesterday" in t):
            return True
        return False

    def is_anomaly_intent(text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["anomaly", "anomalies", "suspicious", "odd", "unusual"])

    def is_transactions_intent(text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["transactions", "transaction", "show", "list", "recent", "last", "history"])

    def is_stats_intent(text: str) -> bool:
        t = text.lower()
        return any(k in t for k in ["how much", "total", "sum", "spent", "spend by", "breakdown"])

    prompt = st.chat_input("Type a finance request… e.g. “add £12 Tesco today” or “show anomalies last 30 days”")
    if prompt:
        add_text("user", prompt)

        days_q = parse_days(prompt, default=int(days))

        try:
            if is_add_intent(prompt):
                amt = parse_amount(prompt)
                if amt is None:
                    add_text("assistant", "I think you want to add a transaction, but I can't find the amount (e.g. £12.50).")
                else:
                    dt = parse_date(prompt) or date.today()
                    merchant = guess_merchant(prompt)
                    proposed = {
                        "date": dt.isoformat(),
                        "merchant": merchant,
                        "amount": float(amt),
                        "category": "Uncategorised",
                        "source": "manual",
                    }
                    st.session_state["pending_tx"] = proposed
                    add_text(
                        "assistant",
                        "I can add this transaction. Please confirm below:\n"
                        f"- Date: {proposed['date']}\n"
                        f"- Merchant: {proposed['merchant']}\n"
                        f"- Amount: £{proposed['amount']:,.2f}\n"
                        f"- Category: {proposed['category']}\n"
                        f"- Source: {proposed['source']}"
                    )

            elif is_anomaly_intent(prompt):
                rows = api_get("/anomalies", params={"days": days_q})
                add_text("assistant", f"Found {len(rows)} anomalies in the last {days_q} days.")
                add_table(f"Anomalies (last {days_q} days)", rows)

            elif is_stats_intent(prompt):
                rows = api_get("/transactions", params={"days": days_q})
                df = pd.DataFrame(rows)
                if df.empty:
                    add_text("assistant", f"No transactions found in the last {days_q} days.")
                else:
                    df["amount"] = pd.to_numeric(df.get("amount"), errors="coerce").fillna(0.0)
                    df["category"] = df.get("category", "Uncategorised").fillna("Uncategorised")
                    total = float(df["amount"].sum())
                    by_cat = df.groupby("category")["amount"].sum().sort_values(ascending=False).head(5)
                    reply = f"Total spend last {days_q} days: £{total:,.2f}. Top categories: " + ", ".join(
                        [f"{c} (£{v:,.2f})" for c, v in by_cat.items()]
                    )
                    add_text("assistant", reply)

            elif is_transactions_intent(prompt):
                rows = api_get("/transactions", params={"days": days_q})
                add_text("assistant", f"Here are {len(rows)} transactions in the last {days_q} days.")
                add_table(f"Transactions (last {days_q} days)", rows)

            else:
                add_text(
                    "assistant",
                    "I can help with finance tasks only. Try:\n"
                    "- “show transactions last 60 days”\n"
                    "- “show anomalies”\n"
                    "- “how much did I spend last 30 days?”\n"
                    "- “add £12 Tesco today” (confirm before saving)"
                )

        except Exception as e:
            add_text("assistant", f"Error: {e}")

        st.rerun()

    # Confirm step for pending transaction
    proposed = st.session_state.get("pending_tx")
    if proposed:
        st.divider()
        st.subheader("Confirm transaction")
        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            st.write("Review / edit before saving:")
            edited_date = st.text_input("Date", value=str(proposed.get("date")), key="chat_tx_date")
            edited_merchant = st.text_input("Merchant", value=str(proposed.get("merchant")), key="chat_tx_merchant")
            edited_category = st.text_input("Category", value=str(proposed.get("category")), key="chat_tx_category")

        with c2:
            edited_amount = st.number_input("Amount", value=float(proposed.get("amount") or 0.0), key="chat_tx_amount")
            edited_source = st.selectbox("Source", ["manual", "receipt", "statement", "import"], index=0, key="chat_tx_source")

        with c3:
            st.write("")
            st.write("")
            if st.button("✅ Save", key="chat_tx_save"):
                try:
                    api_post_json("/transactions", {
                        "date": edited_date,
                        "merchant": edited_merchant,
                        "amount": float(edited_amount),
                        "category": edited_category or "Uncategorised",
                        "source": edited_source,
                    })
                    st.session_state["pending_tx"] = None
                    st.cache_data.clear()

                    # Add a proper closing chat message so user sees confirmation in history
                    add_text("assistant", f"Saved ✅ Added £{float(edited_amount):,.2f} at **{edited_merchant}** on {edited_date}.")
                    st.rerun()
                except Exception as e:
                    st.error(f"Save failed: {e}")

            if st.button("❌ Cancel", key="chat_tx_cancel"):
                st.session_state["pending_tx"] = None
                add_text("assistant", "Cancelled. Nothing was saved.")
                st.rerun()





# # finance_agent/interfaces/app.py
# # Streamlit UI for Finance Agent (Phase 8 MVP)
# # - Keeps Phase 8.1.2 look/feel for Dashboard
# # - Adds Uploads tab (statement PDF + receipt image)
# # - Adds Add Transaction tab (manual)
# #
# # Requires FastAPI running at http://127.0.0.1:8000

# from __future__ import annotations

# from datetime import date as date_cls
# import pandas as pd
# import requests
# import streamlit as st

# # -----------------------------
# # Page config
# # -----------------------------
# st.set_page_config(page_title="Finance Agent", layout="wide")
# st.title("💷 Finance Agent Dashboard")

# # -----------------------------
# # Backend config
# # -----------------------------
# API_BASE = "http://127.0.0.1:8000"

# def api_get(path: str, params: dict | None = None, timeout: int = 30):
#     url = f"{API_BASE}{path}"
#     resp = requests.get(url, params=params or {}, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# def api_post_json(path: str, payload, timeout: int = 60):
#     url = f"{API_BASE}{path}"
#     resp = requests.post(url, json=payload, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# def api_post_file(path: str, file_bytes: bytes, filename: str, mime: str, timeout: int = 120):
#     url = f"{API_BASE}{path}"
#     files = {"file": (filename, file_bytes, mime)}
#     resp = requests.post(url, files=files, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# @st.cache_data(ttl=15, show_spinner=False)
# def load_transactions(days: int) -> pd.DataFrame:
#     data = api_get("/transactions", params={"days": days})
#     df = pd.DataFrame(data)
#     if df.empty:
#         return df

#     if "date" in df.columns:
#         df["date"] = pd.to_datetime(df["date"], errors="coerce")
#     if "amount" in df.columns:
#         df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

#     if "category" in df.columns:
#         df["category"] = df["category"].fillna("Uncategorised")
#     if "merchant" in df.columns:
#         df["merchant"] = df["merchant"].fillna("Unknown")
#     if "source" in df.columns:
#         df["source"] = df["source"].fillna("manual")

#     df = df.sort_values("date", ascending=False, na_position="last")
#     return df

# @st.cache_data(ttl=15, show_spinner=False)
# def load_anomalies(days: int) -> pd.DataFrame:
#     data = api_get("/anomalies", params={"days": days})
#     df = pd.DataFrame(data)
#     if df.empty:
#         return df

#     if "date" in df.columns:
#         df["date"] = pd.to_datetime(df["date"], errors="coerce")
#     if "amount" in df.columns:
#         df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

#     if "category" in df.columns:
#         df["category"] = df["category"].fillna("Uncategorised")
#     if "merchant" in df.columns:
#         df["merchant"] = df["merchant"].fillna("Unknown")
#     if "severity" in df.columns:
#         df["severity"] = df["severity"].fillna("unknown")

#     df = df.sort_values("date", ascending=False, na_position="last")
#     return df


# # -----------------------------
# # Sidebar controls (Phase 8.1.2)
# # -----------------------------
# st.sidebar.header("Controls")

# days = st.sidebar.number_input("Lookback days (API)", min_value=7, max_value=365, value=60, step=1)

# if st.sidebar.button("🔄 Refresh"):
#     st.cache_data.clear()

# with st.spinner("Loading data..."):
#     try:
#         df_tx = load_transactions(days)
#         df_an = load_anomalies(days)
#     except Exception as e:
#         st.error(f"API not reachable: {e}")
#         df_tx = pd.DataFrame()
#         df_an = pd.DataFrame()

# # Date range filter (based on transactions)
# if not df_tx.empty and "date" in df_tx.columns:
#     tx_min = df_tx["date"].min().date() if pd.notna(df_tx["date"].min()) else None
#     tx_max = df_tx["date"].max().date() if pd.notna(df_tx["date"].max()) else None
# else:
#     tx_min, tx_max = None, None

# if tx_min and tx_max:
#     default_start, default_end = tx_min, tx_max
# elif tx_max:
#     default_start, default_end = tx_max, tx_max
# else:
#     default_start = default_end = pd.Timestamp.today().date()

# date_range = st.sidebar.date_input(
#     "Date range (within lookback)",
#     value=(default_start, default_end),
# )

# # Category filter (single-select to preserve 8.1.2 UI)
# cat_options = ["All"]
# if not df_tx.empty and "category" in df_tx.columns:
#     cat_options += sorted([c for c in df_tx["category"].dropna().unique().tolist()])

# selected_category = st.sidebar.selectbox("Category", cat_options)

# # Merchant search
# merchant_q = st.sidebar.text_input("Search merchant", placeholder="e.g. Tesco, Uber, PAY")

# # Apply filters to transactions
# df_tx_f = df_tx.copy()
# if not df_tx_f.empty and "date" in df_tx_f.columns:
#     start_d, end_d = date_range
#     df_tx_f = df_tx_f[
#         (df_tx_f["date"].dt.date >= start_d) &
#         (df_tx_f["date"].dt.date <= end_d)
#     ]

# if selected_category != "All" and "category" in df_tx_f.columns:
#     df_tx_f = df_tx_f[df_tx_f["category"] == selected_category]

# if merchant_q and "merchant" in df_tx_f.columns:
#     df_tx_f = df_tx_f[df_tx_f["merchant"].str.contains(merchant_q, case=False, na=False)]

# # Apply similar filters to anomalies
# df_an_f = df_an.copy()
# if not df_an_f.empty and "date" in df_an_f.columns:
#     start_d, end_d = date_range
#     df_an_f = df_an_f[
#         (df_an_f["date"].dt.date >= start_d) &
#         (df_an_f["date"].dt.date <= end_d)
#     ]
# if selected_category != "All" and "category" in df_an_f.columns:
#     df_an_f = df_an_f[df_an_f["category"] == selected_category]
# if merchant_q and "merchant" in df_an_f.columns:
#     df_an_f = df_an_f[df_an_f["merchant"].str.contains(merchant_q, case=False, na=False)]

# if not df_an_f.empty and "severity" in df_an_f.columns:
#     severities = sorted(df_an_f["severity"].dropna().unique().tolist())
#     chosen_sev = st.sidebar.multiselect("Anomaly severity", severities, default=severities)
#     if chosen_sev:
#         df_an_f = df_an_f[df_an_f["severity"].isin(chosen_sev)]


# # -----------------------------
# # Tabs
# # -----------------------------
# tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📤 Uploads", "➕ Add Transaction"])

# # -----------------------------
# # Dashboard tab (keeps 8.1.2 layout)
# # -----------------------------
# with tab1:
#     colm1, colm2, colm3, colm4 = st.columns(4)

#     tx_count = int(df_tx_f.shape[0]) if not df_tx_f.empty else 0
#     an_count = int(df_an_f.shape[0]) if not df_an_f.empty else 0
#     total_spend = float(df_tx_f["amount"].sum()) if (not df_tx_f.empty and "amount" in df_tx_f.columns) else 0.0
#     unique_merchants = int(df_tx_f["merchant"].nunique()) if (not df_tx_f.empty and "merchant" in df_tx_f.columns) else 0

#     colm1.metric("Transactions", tx_count)
#     colm2.metric("Anomalies", an_count)
#     colm3.metric("Total amount (lookback)", f"£{total_spend:,.2f}")
#     colm4.metric("Unique merchants", unique_merchants)

#     st.divider()

#     st.subheader("📈 Insights")

#     if df_tx_f.empty:
#         st.info("No transactions found for the selected lookback window.")
#     else:
#         c1, c2 = st.columns(2)

#         with c1:
#             st.caption("Spend by category")
#             if "category" in df_tx_f.columns and "amount" in df_tx_f.columns:
#                 by_cat = (
#                     df_tx_f.dropna(subset=["category", "amount"])
#                         .groupby("category", as_index=True)["amount"]
#                         .sum()
#                         .sort_values(ascending=False)
#                 )
#                 st.bar_chart(by_cat, height=280)
#             else:
#                 st.warning("Missing 'category' or 'amount' fields in transactions.")

#         with c2:
#             st.caption("Spend over time")
#             if "date" in df_tx_f.columns and "amount" in df_tx_f.columns:
#                 by_day = (
#                     df_tx_f.dropna(subset=["date", "amount"])
#                         .groupby(df_tx_f["date"].dt.date, as_index=True)["amount"]
#                         .sum()
#                         .sort_index()
#                 )
#                 st.line_chart(by_day, height=280)
#             else:
#                 st.warning("Missing 'date' or 'amount' fields in transactions.")

#         c3, c4 = st.columns(2)

#         with c3:
#             st.caption("Top merchants (by total amount)")
#             if "merchant" in df_tx_f.columns and "amount" in df_tx_f.columns:
#                 top_merchants = (
#                     df_tx_f.dropna(subset=["merchant", "amount"])
#                         .groupby("merchant", as_index=True)["amount"]
#                         .sum()
#                         .sort_values(ascending=False)
#                         .head(10)
#                 )
#                 st.bar_chart(top_merchants, height=280)
#             else:
#                 st.warning("Missing 'merchant' or 'amount' fields in transactions.")

#         with c4:
#             st.caption("Anomaly counts")
#             if df_an_f.empty:
#                 st.info("No anomalies detected in this window.")
#             else:
#                 if "severity" in df_an_f.columns:
#                     counts = df_an_f["severity"].value_counts()
#                     st.bar_chart(counts, height=280)
#                 else:
#                     st.bar_chart(pd.Series({"anomalies": len(df_an_f)}), height=280)

#     st.divider()

#     colA, colB = st.columns(2)

#     with colA:
#         st.subheader("📒 Transactions")
#         if df_tx_f.empty:
#             st.info("No transactions yet.")
#         else:
#             show_cols = [c for c in ["date", "merchant", "amount", "category", "source"] if c in df_tx_f.columns]
#             st.dataframe(df_tx_f[show_cols], width="stretch", hide_index=True)

#     with colB:
#         st.subheader("⚠️ Anomalies")
#         if df_an_f.empty:
#             st.info("No anomalies yet.")
#         else:
#             show_cols = [c for c in ["date", "merchant", "amount", "category", "severity", "reason"] if c in df_an_f.columns]
#             st.dataframe(df_an_f[show_cols], width="stretch", hide_index=True)


# # -----------------------------
# # Uploads tab (Phase 8.1.3)
# # -----------------------------
# with tab2:
#     st.subheader("Upload bank statement PDF")
#     pdf = st.file_uploader("Choose a PDF statement", type=["pdf"], key="pdf_upload")

#     if "statement_candidates" not in st.session_state:
#         st.session_state["statement_candidates"] = None

#     if pdf is not None and st.button("Parse statement"):
#         try:
#             cand = api_post_file("/statements/parse", pdf.getvalue(), pdf.name, "application/pdf", timeout=180)
#             st.session_state["statement_candidates"] = cand
#             if isinstance(cand, list) and len(cand) > 0:
#                 st.success(f"Found {len(cand)} candidate transactions.")
#             else:
#                 st.warning("Parsed successfully, but found 0 candidate transactions.")
#         except Exception as e:
#             st.error(f"Statement parse failed: {e}")

#     cand = st.session_state.get("statement_candidates")
#     if cand is not None:
#         if isinstance(cand, list) and len(cand) > 0:
#             df_c = pd.DataFrame(cand)
#             st.dataframe(df_c, width="stretch", hide_index=True)

#             selected_idx = st.multiselect(
#                 "Select transactions to ingest",
#                 options=list(range(len(cand))),
#                 default=list(range(len(cand))),
#                 format_func=lambda i: f"{cand[i].get('date')} | {cand[i].get('merchant')} | £{cand[i].get('amount')}",
#             )
#             if st.button("Ingest selected transactions"):
#                 try:
#                     payload = [cand[i] for i in selected_idx]
#                     res = api_post_json("/statements/ingest", payload, timeout=120)
#                     st.success(f"Added {res.get('added', 0)} transactions to finance.db")
#                     st.session_state["statement_candidates"] = None
#                     st.cache_data.clear()
#                 except Exception as e:
#                     st.error(f"Ingest failed: {e}")
#         else:
#             st.info("No statement candidates to display yet. Upload a PDF and click **Parse statement**.")

#     st.divider()

#     st.subheader("Upload receipt image")
#     img = st.file_uploader("Choose a receipt image", type=["png", "jpg", "jpeg"], key="receipt_upload")

#     if "receipt_parsed" not in st.session_state:
#         st.session_state["receipt_parsed"] = None

#     if img is not None and st.button("Parse receipt"):
#         try:
#             parsed = api_post_file("/receipts/parse", img.getvalue(), img.name, "image/png", timeout=180)
#             st.session_state["receipt_parsed"] = parsed
#             st.success("Receipt parsed (review and edit below).")
#         except requests.HTTPError as e:
#             # Show API error details if present
#             detail = ""
#             try:
#                 detail = e.response.json().get("detail", "")
#             except Exception:
#                 pass
#             st.error(f"Receipt parse failed: {detail or e}")
#         except Exception as e:
#             st.error(f"Receipt parse failed: {e}")

#     parsed = st.session_state.get("receipt_parsed")
#     if parsed:
#         if parsed.get("warning"):
#             st.warning(parsed["warning"])

#         st.write("Review / edit fields before saving:")
#         col1, col2 = st.columns(2)
#         with col1:
#             r_date = st.text_input("Date (YYYY-MM-DD)", value=parsed.get("date") or "")
#             r_merchant = st.text_input("Merchant", value=parsed.get("merchant") or "")
#         with col2:
#             r_amount = st.number_input("Total amount", value=float(parsed.get("total_amount") or 0.0))
#             r_category = st.text_input("Category", value=parsed.get("category") or "Uncategorised")

#         with st.expander("Raw OCR text"):
#             st.code(parsed.get("raw_text") or "", language="text")

#         if st.button("Save receipt as transaction"):
#             try:
#                 api_post_json(
#                     "/receipts/ingest",
#                     {"date": r_date, "merchant": r_merchant, "total_amount": float(r_amount), "category": r_category},
#                     timeout=60,
#                 )
#                 st.success("Receipt saved to finance.db")
#                 st.session_state["receipt_parsed"] = None
#                 st.cache_data.clear()
#             except Exception as e:
#                 st.error(f"Save failed: {e}")


# # -----------------------------
# # Add Transaction tab
# # -----------------------------
# with tab3:
#     st.subheader("Add transaction (manual)")

#     with st.form("add_tx_form"):
#         c1, c2 = st.columns(2)
#         with c1:
#             f_date = st.date_input("Date", value=pd.Timestamp.today().date()).strftime("%Y-%m-%d")
#             f_merchant = st.text_input("Merchant")
#         with c2:
#             f_amount = st.number_input("Amount", value=0.0)
#             f_category = st.text_input("Category", value="Uncategorised")

#         f_source = st.selectbox("Source", ["manual", "receipt", "statement", "import"], index=0)
#         submitted = st.form_submit_button("Add transaction")

#     if submitted:
#         try:
#             api_post_json(
#                 "/transactions",
#                 {"date": f_date, "merchant": f_merchant, "amount": float(f_amount), "category": f_category, "source": f_source},
#                 timeout=60,
#             )
#             st.success("Transaction added.")
#             st.cache_data.clear()
#         except Exception as e:
#             st.error(f"Add failed: {e}")
