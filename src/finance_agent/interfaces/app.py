# Streamlit UI for Finance Agent
# - Calls our FastAPI backend (running locally)
# - Shows Transactions + Anomalies
# - Keeps it simple and visible

from __future__ import annotations

import requests
import pandas as pd
import streamlit as st

# ---- Page config ----
st.set_page_config(page_title="Finance Agent", layout="wide")
st.title("💷 Finance Agent Dashboard")

# ---- Backend config ----
API_BASE = "http://127.0.0.1:8000"


def api_get(path: str, params: dict | None = None, timeout: int = 30):
    """Simple GET helper for our FastAPI backend."""
    url = f"{API_BASE}{path}"
    resp = requests.get(url, params=params or {}, timeout=timeout)
    resp.raise_for_status()
    return resp.json()

@st.cache_data(ttl=15, show_spinner=False)
def load_transactions(days: int) -> pd.DataFrame:
    """Fetch transactions from the API and return a clean DataFrame."""
    data = api_get("/transactions", params={"days": days})
    df = pd.DataFrame(data)
    if df.empty:
        return df

    # Normalise types
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")
    if "amount" in df.columns:
        df["amount"] = pd.to_numeric(df["amount"], errors="coerce")

    # Basic fill for optional fields
    if "category" in df.columns:
        df["category"] = df["category"].fillna("Uncategorised")
    if "merchant" in df.columns:
        df["merchant"] = df["merchant"].fillna("Unknown")

    df = df.sort_values("date", ascending=False, na_position="last")
    return df

@st.cache_data(ttl=15, show_spinner=False)
def load_anomalies(days: int) -> pd.DataFrame:
    """Fetch anomalies from the API and return a clean DataFrame."""
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
# Sidebar controls
# -----------------------------
st.sidebar.header("Controls")
days = st.sidebar.number_input("Lookback days", min_value=7, max_value=365, value=60, step=1)

# Fetch data
with st.spinner("Loading data..."):
    df_tx = load_transactions(days)
    df_an = load_anomalies(days)

# -----------------------------
# Quick health checks / metrics
# -----------------------------
colm1, colm2, colm3, colm4 = st.columns(4)

tx_count = int(df_tx.shape[0]) if not df_tx.empty else 0
an_count = int(df_an.shape[0]) if not df_an.empty else 0
total_spend = float(df_tx["amount"].sum()) if (not df_tx.empty and "amount" in df_tx.columns) else 0.0
unique_merchants = int(df_tx["merchant"].nunique()) if (not df_tx.empty and "merchant" in df_tx.columns) else 0

colm1.metric("Transactions", tx_count)
colm2.metric("Anomalies", an_count)
colm3.metric("Total amount (lookback)", f"£{total_spend:,.2f}")
colm4.metric("Unique merchants", unique_merchants)

st.divider()

# -----------------------------
# Charts (Phase 8.1.1)
# -----------------------------
st.subheader("📈 Insights")

if df_tx.empty:
    st.info("No transactions found for the selected lookback window.")
else:
    c1, c2 = st.columns(2)

    # (1) Spend by category (bar)
    with c1:
        st.caption("Spend by category")
        if "category" in df_tx.columns and "amount" in df_tx.columns:
            by_cat = (
                df_tx.dropna(subset=["category", "amount"])
                    .groupby("category", as_index=True)["amount"]
                    .sum()
                    .sort_values(ascending=False)
            )
            st.bar_chart(by_cat, height=280)
        else:
            st.warning("Missing 'category' or 'amount' fields in transactions.")

    # (2) Spend over time (line)
    with c2:
        st.caption("Spend over time")
        if "date" in df_tx.columns and "amount" in df_tx.columns:
            by_day = (
                df_tx.dropna(subset=["date", "amount"])
                    .groupby(df_tx["date"].dt.date, as_index=True)["amount"]
                    .sum()
                    .sort_index()
            )
            st.line_chart(by_day, height=280)
        else:
            st.warning("Missing 'date' or 'amount' fields in transactions.")

    c3, c4 = st.columns(2)

    # (3) Top merchants (bar)
    with c3:
        st.caption("Top merchants (by total amount)")
        if "merchant" in df_tx.columns and "amount" in df_tx.columns:
            top_merchants = (
                df_tx.dropna(subset=["merchant", "amount"])
                    .groupby("merchant", as_index=True)["amount"]
                    .sum()
                    .sort_values(ascending=False)
                    .head(10)
            )
            st.bar_chart(top_merchants, height=280)
        else:
            st.warning("Missing 'merchant' or 'amount' fields in transactions.")

    # (4) Anomaly counts (bar)
    with c4:
        st.caption("Anomaly counts")
        if df_an.empty:
            st.info("No anomalies detected in this window.")
        else:
            if "severity" in df_an.columns:
                counts = df_an["severity"].value_counts()
                st.bar_chart(counts, height=280)
            else:
                # Fallback if your anomaly schema doesn't have severity
                st.bar_chart(pd.Series({"anomalies": len(df_an)}), height=280)

st.divider()

# -----------------------------
# Tables
# -----------------------------
colA, colB = st.columns(2)

with colA:
    st.subheader("📒 Transactions")
    if df_tx.empty:
        st.info("No transactions yet.")
    else:
        # Display a friendly table
        show_cols = [c for c in ["date", "merchant", "amount", "category", "source"] if c in df_tx.columns]
        st.dataframe(df_tx[show_cols], width="stretch", hide_index=True)

with colB:
    st.subheader("⚠️ Anomalies")
    if df_an.empty:
        st.info("No anomalies yet.")
    else:
        show_cols = [c for c in ["date", "merchant", "amount", "category", "severity", "reason"] if c in df_an.columns]
        st.dataframe(df_an[show_cols], width="stretch", hide_index=True)


# # ---- Helper: safe GET ----
# def api_get(path: str, params: dict | None = None):
#     url = f"{API_BASE}{path}"
#     r = requests.get(url, params=params, timeout=20)
#     r.raise_for_status()
#     return r.json()

# # ---- Sidebar controls ----
# st.sidebar.header("Controls")
# days = st.sidebar.number_input("Lookback days", min_value=1, max_value=365, value=60)

# colA, colB = st.columns(2)

# # ---- Transactions ----
# with colA:
#     st.subheader("📒 Transactions")
#     try:
#         tx = api_get("/transactions", params={"days": days})
#         df_tx = pd.DataFrame(tx)
#         st.dataframe(df_tx, width="stretch", hide_index=True)
#     except Exception as e:
#         st.error(f"Transactions load failed: {e}")

# # ---- Anomalies ----
# with colB:
#     st.subheader("⚠️ Anomalies")
#     try:
#         an = api_get("/anomalies", params={"days": days})
#         df_an = pd.DataFrame(an)
#         st.dataframe(df_an, width="stretch", hide_index=True)
#     except Exception as e:
#         st.error(f"Anomalies load failed: {e}")
