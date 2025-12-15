# finance_agent/interfaces/app.py
# Streamlit UI for Finance Agent (Phase 8 MVP)
# - Keeps Phase 8.1.2 look/feel for Dashboard
# - Adds Uploads tab (statement PDF + receipt image)
# - Adds Add Transaction tab (manual)
#
# Requires FastAPI running at http://127.0.0.1:8000

from __future__ import annotations

from datetime import date as date_cls
import pandas as pd
import requests
import streamlit as st

# -----------------------------
# Page config
# -----------------------------
st.set_page_config(page_title="Finance Agent", layout="wide")
st.title("💷 Finance Agent Dashboard")

# -----------------------------
# Backend config
# -----------------------------
API_BASE = "http://127.0.0.1:8000"

def api_get(path: str, params: dict | None = None, timeout: int = 30):
    url = f"{API_BASE}{path}"
    resp = requests.get(url, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def api_post_json(path: str, payload, timeout: int = 60):
    url = f"{API_BASE}{path}"
    resp = requests.post(url, json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

def api_post_file(path: str, file_bytes: bytes, filename: str, mime: str, timeout: int = 120):
    url = f"{API_BASE}{path}"
    files = {"file": (filename, file_bytes, mime)}
    resp = requests.post(url, files=files, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

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
        df["source"] = df["source"].fillna("manual")

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
# Sidebar controls (Phase 8.1.2)
# -----------------------------
st.sidebar.header("Controls")

days = st.sidebar.number_input("Lookback days (API)", min_value=7, max_value=365, value=60, step=1)

if st.sidebar.button("🔄 Refresh"):
    st.cache_data.clear()

with st.spinner("Loading data..."):
    try:
        df_tx = load_transactions(days)
        df_an = load_anomalies(days)
    except Exception as e:
        st.error(f"API not reachable: {e}")
        df_tx = pd.DataFrame()
        df_an = pd.DataFrame()

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

date_range = st.sidebar.date_input(
    "Date range (within lookback)",
    value=(default_start, default_end),
)

# Category filter (single-select to preserve 8.1.2 UI)
cat_options = ["All"]
if not df_tx.empty and "category" in df_tx.columns:
    cat_options += sorted([c for c in df_tx["category"].dropna().unique().tolist()])

selected_category = st.sidebar.selectbox("Category", cat_options)

# Merchant search
merchant_q = st.sidebar.text_input("Search merchant", placeholder="e.g. Tesco, Uber, PAY")

# Apply filters to transactions
df_tx_f = df_tx.copy()
if not df_tx_f.empty and "date" in df_tx_f.columns:
    start_d, end_d = date_range
    df_tx_f = df_tx_f[
        (df_tx_f["date"].dt.date >= start_d) &
        (df_tx_f["date"].dt.date <= end_d)
    ]

if selected_category != "All" and "category" in df_tx_f.columns:
    df_tx_f = df_tx_f[df_tx_f["category"] == selected_category]

if merchant_q and "merchant" in df_tx_f.columns:
    df_tx_f = df_tx_f[df_tx_f["merchant"].str.contains(merchant_q, case=False, na=False)]

# Apply similar filters to anomalies
df_an_f = df_an.copy()
if not df_an_f.empty and "date" in df_an_f.columns:
    start_d, end_d = date_range
    df_an_f = df_an_f[
        (df_an_f["date"].dt.date >= start_d) &
        (df_an_f["date"].dt.date <= end_d)
    ]
if selected_category != "All" and "category" in df_an_f.columns:
    df_an_f = df_an_f[df_an_f["category"] == selected_category]
if merchant_q and "merchant" in df_an_f.columns:
    df_an_f = df_an_f[df_an_f["merchant"].str.contains(merchant_q, case=False, na=False)]

if not df_an_f.empty and "severity" in df_an_f.columns:
    severities = sorted(df_an_f["severity"].dropna().unique().tolist())
    chosen_sev = st.sidebar.multiselect("Anomaly severity", severities, default=severities)
    if chosen_sev:
        df_an_f = df_an_f[df_an_f["severity"].isin(chosen_sev)]


# -----------------------------
# Tabs
# -----------------------------
tab1, tab2, tab3 = st.tabs(["📊 Dashboard", "📤 Uploads", "➕ Add Transaction"])

# -----------------------------
# Dashboard tab (keeps 8.1.2 layout)
# -----------------------------
with tab1:
    colm1, colm2, colm3, colm4 = st.columns(4)

    tx_count = int(df_tx_f.shape[0]) if not df_tx_f.empty else 0
    an_count = int(df_an_f.shape[0]) if not df_an_f.empty else 0
    total_spend = float(df_tx_f["amount"].sum()) if (not df_tx_f.empty and "amount" in df_tx_f.columns) else 0.0
    unique_merchants = int(df_tx_f["merchant"].nunique()) if (not df_tx_f.empty and "merchant" in df_tx_f.columns) else 0

    colm1.metric("Transactions", tx_count)
    colm2.metric("Anomalies", an_count)
    colm3.metric("Total amount (lookback)", f"£{total_spend:,.2f}")
    colm4.metric("Unique merchants", unique_merchants)

    st.divider()

    st.subheader("📈 Insights")

    if df_tx_f.empty:
        st.info("No transactions found for the selected lookback window.")
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
with tab2:
    st.subheader("Upload bank statement PDF")
    pdf = st.file_uploader("Choose a PDF statement", type=["pdf"], key="pdf_upload")

    if "statement_candidates" not in st.session_state:
        st.session_state["statement_candidates"] = None

    if pdf is not None and st.button("Parse statement"):
        try:
            cand = api_post_file("/statements/parse", pdf.getvalue(), pdf.name, "application/pdf", timeout=180)
            st.session_state["statement_candidates"] = cand
            if isinstance(cand, list) and len(cand) > 0:
                st.success(f"Found {len(cand)} candidate transactions.")
            else:
                st.warning("Parsed successfully, but found 0 candidate transactions.")
        except Exception as e:
            st.error(f"Statement parse failed: {e}")

    cand = st.session_state.get("statement_candidates")
    if cand is not None:
        if isinstance(cand, list) and len(cand) > 0:
            df_c = pd.DataFrame(cand)
            st.dataframe(df_c, width="stretch", hide_index=True)

            selected_idx = st.multiselect(
                "Select transactions to ingest",
                options=list(range(len(cand))),
                default=list(range(len(cand))),
                format_func=lambda i: f"{cand[i].get('date')} | {cand[i].get('merchant')} | £{cand[i].get('amount')}",
            )
            if st.button("Ingest selected transactions"):
                try:
                    payload = [cand[i] for i in selected_idx]
                    res = api_post_json("/statements/ingest", payload, timeout=120)
                    st.success(f"Added {res.get('added', 0)} transactions to finance.db")
                    st.session_state["statement_candidates"] = None
                    st.cache_data.clear()
                except Exception as e:
                    st.error(f"Ingest failed: {e}")
        else:
            st.info("No statement candidates to display yet. Upload a PDF and click **Parse statement**.")

    st.divider()

    st.subheader("Upload receipt image")
    img = st.file_uploader("Choose a receipt image", type=["png", "jpg", "jpeg"], key="receipt_upload")

    if "receipt_parsed" not in st.session_state:
        st.session_state["receipt_parsed"] = None

    if img is not None and st.button("Parse receipt"):
        try:
            parsed = api_post_file("/receipts/parse", img.getvalue(), img.name, "image/png", timeout=180)
            st.session_state["receipt_parsed"] = parsed
            st.success("Receipt parsed (review and edit below).")
        except requests.HTTPError as e:
            # Show API error details if present
            detail = ""
            try:
                detail = e.response.json().get("detail", "")
            except Exception:
                pass
            st.error(f"Receipt parse failed: {detail or e}")
        except Exception as e:
            st.error(f"Receipt parse failed: {e}")

    parsed = st.session_state.get("receipt_parsed")
    if parsed:
        if parsed.get("warning"):
            st.warning(parsed["warning"])

        st.write("Review / edit fields before saving:")
        col1, col2 = st.columns(2)
        with col1:
            r_date = st.text_input("Date (YYYY-MM-DD)", value=parsed.get("date") or "")
            r_merchant = st.text_input("Merchant", value=parsed.get("merchant") or "")
        with col2:
            r_amount = st.number_input("Total amount", value=float(parsed.get("total_amount") or 0.0))
            r_category = st.text_input("Category", value=parsed.get("category") or "Uncategorised")

        with st.expander("Raw OCR text"):
            st.code(parsed.get("raw_text") or "", language="text")

        if st.button("Save receipt as transaction"):
            try:
                api_post_json(
                    "/receipts/ingest",
                    {"date": r_date, "merchant": r_merchant, "total_amount": float(r_amount), "category": r_category},
                    timeout=60,
                )
                st.success("Receipt saved to finance.db")
                st.session_state["receipt_parsed"] = None
                st.cache_data.clear()
            except Exception as e:
                st.error(f"Save failed: {e}")


# -----------------------------
# Add Transaction tab
# -----------------------------
with tab3:
    st.subheader("Add transaction (manual)")

    with st.form("add_tx_form"):
        c1, c2 = st.columns(2)
        with c1:
            f_date = st.date_input("Date", value=pd.Timestamp.today().date()).strftime("%Y-%m-%d")
            f_merchant = st.text_input("Merchant")
        with c2:
            f_amount = st.number_input("Amount", value=0.0)
            f_category = st.text_input("Category", value="Uncategorised")

        f_source = st.selectbox("Source", ["manual", "receipt", "statement", "import"], index=0)
        submitted = st.form_submit_button("Add transaction")

    if submitted:
        try:
            api_post_json(
                "/transactions",
                {"date": f_date, "merchant": f_merchant, "amount": float(f_amount), "category": f_category, "source": f_source},
                timeout=60,
            )
            st.success("Transaction added.")
            st.cache_data.clear()
        except Exception as e:
            st.error(f"Add failed: {e}")







# # finance_agent/interfaces/app.py
# # Streamlit UI for Finance Agent (Phase 8 MVP)
# # ✅ Keeps Phase 8.1.2 layout (filters + metrics + charts + tables)
# # ✅ Adds Phase 8.1.3 tabs: Uploads (PDF statement + receipt image) + Add Transaction
# # ✅ Fixes spend-over-time chart KeyError by using the correct index/series.

# from __future__ import annotations

# from datetime import date
# from typing import Any

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
# API_BASE = "http://127.0.0.1:8000"  # FastAPI base URL (local)

# # -----------------------------
# # API helpers
# # -----------------------------
# def api_get(path: str, params: dict | None = None, timeout: int = 30) -> Any:
#     url = f"{API_BASE}{path}"
#     resp = requests.get(url, params=params or {}, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# def api_post_json(path: str, payload: Any, timeout: int = 60) -> Any:
#     url = f"{API_BASE}{path}"
#     resp = requests.post(url, json=payload, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# def api_post_file(path: str, file_bytes: bytes, filename: str, mime: str, timeout: int = 180) -> Any:
#     url = f"{API_BASE}{path}"
#     files = {"file": (filename, file_bytes, mime)}
#     resp = requests.post(url, files=files, timeout=timeout)
#     resp.raise_for_status()
#     return resp.json()

# # -----------------------------
# # Cached loaders (Phase 8.1.2 style)
# # -----------------------------
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
#         df["source"] = df["source"].fillna("unknown")

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
#     if "reason" in df.columns:
#         df["reason"] = df["reason"].fillna("")

#     df = df.sort_values("date", ascending=False, na_position="last")
#     return df

# def clear_cache_and_rerun():
#     st.cache_data.clear()
#     st.rerun()

# # -----------------------------
# # Sidebar controls (Phase 8.1.2 style)
# # -----------------------------
# st.sidebar.header("Controls")

# days = st.sidebar.number_input(
#     "Lookback days (API)",
#     min_value=7,
#     max_value=365,
#     value=60,
#     step=1,
# )

# if st.sidebar.button("🔄 Refresh"):
#     clear_cache_and_rerun()

# # -----------------------------
# # Load data
# # -----------------------------
# api_ok = True
# try:
#     with st.spinner("Loading data..."):
#         df_tx = load_transactions(int(days))
#         df_an = load_anomalies(int(days))
# except Exception as e:
#     api_ok = False
#     st.error(f"API not reachable: {e}")
#     df_tx = pd.DataFrame()
#     df_an = pd.DataFrame()

# # -----------------------------
# # Filters + search + date range (Phase 8.1.2)
# # -----------------------------
# if not df_tx.empty and "date" in df_tx.columns:
#     tx_min = df_tx["date"].min()
#     tx_max = df_tx["date"].max()
#     tx_min_d = tx_min.date() if pd.notna(tx_min) else None
#     tx_max_d = tx_max.date() if pd.notna(tx_max) else None
# else:
#     tx_min_d, tx_max_d = None, None

# if tx_min_d and tx_max_d:
#     default_start, default_end = tx_min_d, tx_max_d
# elif tx_max_d:
#     default_start, default_end = tx_max_d, tx_max_d
# else:
#     today = date.today()
#     default_start, default_end = today, today

# date_range = st.sidebar.date_input(
#     "Date range (within lookback)",
#     value=(default_start, default_end),
# )

# cat_options = ["All"]
# if not df_tx.empty and "category" in df_tx.columns:
#     cat_options += sorted([c for c in df_tx["category"].dropna().unique().tolist()])

# selected_category = st.sidebar.selectbox("Category", cat_options)

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
# # Tabs (Phase 8.1.3 added without changing Dashboard layout)
# # -----------------------------
# tab_dash, tab_uploads, tab_add = st.tabs(["📊 Dashboard", "📤 Uploads", "➕ Add Transaction"])

# # =============================
# # Dashboard tab (KEEP 8.1.2 look)
# # =============================
# with tab_dash:
#     # Metrics
#     colm1, colm2, colm3, colm4 = st.columns(4)

#     tx_count = int(df_tx_f.shape[0]) if not df_tx_f.empty else 0
#     an_count = int(df_an_f.shape[0]) if not df_an_f.empty else 0
#     total_spend = float(df_tx_f["amount"].sum()) if (not df_tx_f.empty and "amount" in df_tx_f.columns) else 0.0
#     unique_merchants = int(df_tx_f["merchant"].nunique()) if (not df_tx_f.empty and "merchant" in df_tx_f.columns) else 0

#     colm1.metric("Transactions", tx_count)
#     colm2.metric("Anomalies", an_count)
#     colm3.metric("Total amount (filtered)", f"£{total_spend:,.2f}")
#     colm4.metric("Unique merchants", unique_merchants)

#     st.divider()

#     # Charts
#     st.subheader("📈 Insights")

#     if df_tx_f.empty:
#         st.info("No transactions found for the selected window.")
#     else:
#         c1, c2 = st.columns(2)

#         # (1) Spend by category (bar)
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

#         # (2) Spend over time (line) — FIXED (use series index, no 'date' column expected)
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

#         # (3) Top merchants (bar)
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

#         # (4) Anomaly counts (bar)
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

#     # Tables
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

# # =============================
# # Uploads tab (Phase 8.1.3)
# # =============================
# with tab_uploads:
#     if not api_ok:
#         st.warning("Start the API first: uv run uvicorn finance_agent.interfaces.api:app --reload")
#     else:
#         st.subheader("Upload bank statement PDF")

#         pdf = st.file_uploader("Choose a PDF statement", type=["pdf"], key="pdf_upload")
#         if "statement_candidates" not in st.session_state:
#             st.session_state["statement_candidates"] = None

#         colp1, colp2 = st.columns([1, 1])
#         with colp1:
#             if pdf is not None and st.button("Parse statement"):
#                 try:
#                     cand = api_post_file("/statements/parse", pdf.getvalue(), pdf.name, "application/pdf")
#                     st.session_state["statement_candidates"] = cand
#                     st.success(f"Found {len(cand)} candidate transactions.")
#                 except Exception as e:
#                     st.error(f"Statement parse failed: {e}")

#         cand = st.session_state.get("statement_candidates")
#         if cand:
#             df_c = pd.DataFrame(cand)
#             st.dataframe(df_c, width="stretch", hide_index=True)

#             st.write("Select which ones to ingest:")
#             selected_idx = st.multiselect(
#                 "Transactions",
#                 options=list(range(len(cand))),
#                 default=list(range(len(cand))),
#                 format_func=lambda i: f"{cand[i].get('date')} | {cand[i].get('merchant')} | £{cand[i].get('amount')}",
#             )

#             with colp2:
#                 if st.button("Ingest selected statements"):
#                     try:
#                         payload = [cand[i] for i in selected_idx]
#                         res = api_post_json("/statements/ingest", payload)
#                         st.success(f"Added {res.get('added', 0)} transactions to finance.db")
#                         st.session_state["statement_candidates"] = None
#                         clear_cache_and_rerun()
#                     except Exception as e:
#                         st.error(f"Ingest failed: {e}")

#         st.divider()

#         st.subheader("Upload receipt image")

#         img = st.file_uploader("Choose a receipt image", type=["png", "jpg", "jpeg"], key="receipt_upload")
#         if "receipt_parsed" not in st.session_state:
#             st.session_state["receipt_parsed"] = None

#         if img is not None and st.button("Parse receipt"):
#             try:
#                 mime = "image/png" if img.type is None else img.type
#                 parsed = api_post_file("/receipts/parse", img.getvalue(), img.name, mime)
#                 st.session_state["receipt_parsed"] = parsed
#                 st.success("Receipt parsed.")
#             except Exception as e:
#                 st.error(f"Receipt parse failed: {e}")

#         parsed = st.session_state.get("receipt_parsed")
#         if parsed:
#             st.write("Review / edit fields before saving:")
#             col1, col2 = st.columns(2)
#             with col1:
#                 r_date = st.text_input("Date (YYYY-MM-DD)", value=parsed.get("date") or "")
#                 r_merchant = st.text_input("Merchant", value=parsed.get("merchant") or "")
#             with col2:
#                 r_amount = st.number_input("Total amount", value=float(parsed.get("total_amount") or 0.0))
#                 r_category = st.text_input("Category", value=parsed.get("category") or "Uncategorised")

#             if st.button("Save receipt as transaction"):
#                 try:
#                     api_post_json("/receipts/ingest", {
#                         "date": r_date,
#                         "merchant": r_merchant,
#                         "total_amount": float(r_amount),
#                         "category": r_category,
#                     })
#                     st.success("Receipt saved to finance.db")
#                     st.session_state["receipt_parsed"] = None
#                     clear_cache_and_rerun()
#                 except Exception as e:
#                     st.error(f"Save failed: {e}")

# # =============================
# # Add transaction tab (Phase 8.1.3)
# # =============================
# with tab_add:
#     if not api_ok:
#         st.warning("Start the API first: uv run uvicorn finance_agent.interfaces.api:app --reload")
#     else:
#         st.subheader("Add transaction (manual)")

#         with st.form("add_tx_form"):
#             c1, c2 = st.columns(2)
#             with c1:
#                 f_date = st.date_input("Date").strftime("%Y-%m-%d")
#                 f_merchant = st.text_input("Merchant")
#             with c2:
#                 f_amount = st.number_input("Amount", value=0.0)
#                 f_category = st.text_input("Category", value="Uncategorised")
#             f_source = st.selectbox("Source", ["manual", "receipt", "statement", "import"])
#             submitted = st.form_submit_button("Add transaction")

#         if submitted:
#             try:
#                 api_post_json("/transactions", {
#                     "date": f_date,
#                     "merchant": f_merchant,
#                     "amount": float(f_amount),
#                     "category": f_category,
#                     "source": f_source,
#                 })
#                 st.success("Transaction added.")
#                 clear_cache_and_rerun()
#             except Exception as e:
#                 st.error(f"Add failed: {e}")
