# Streamlit UI for Finance Agent
# - Calls our FastAPI backend (running locally)
# - Shows Transactions + Anomalies
# - Keeps it simple and visible

import requests
import pandas as pd
import streamlit as st

# ---- Page config ----
st.set_page_config(page_title="Finance Agent", layout="wide")
st.title("💷 Finance Agent Dashboard")

# ---- Backend config ----
API_BASE = "http://127.0.0.1:8000"

# ---- Helper: safe GET ----
def api_get(path: str, params: dict | None = None):
    url = f"{API_BASE}{path}"
    r = requests.get(url, params=params, timeout=20)
    r.raise_for_status()
    return r.json()

# ---- Sidebar controls ----
st.sidebar.header("Controls")
days = st.sidebar.number_input("Lookback days", min_value=1, max_value=365, value=60)

colA, colB = st.columns(2)

# ---- Transactions ----
with colA:
    st.subheader("📒 Transactions")
    try:
        tx = api_get("/transactions", params={"days": days})
        df_tx = pd.DataFrame(tx)
        st.dataframe(df_tx, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Transactions load failed: {e}")

# ---- Anomalies ----
with colB:
    st.subheader("⚠️ Anomalies")
    try:
        an = api_get("/anomalies", params={"days": days})
        df_an = pd.DataFrame(an)
        st.dataframe(df_an, use_container_width=True, hide_index=True)
    except Exception as e:
        st.error(f"Anomalies load failed: {e}")
