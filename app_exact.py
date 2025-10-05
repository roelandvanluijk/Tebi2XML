# app_exact.py
import os, json
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_oauth import OAuth2Component
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from pathlib import Path

from tebi_books_transformers.io_reader import load_file
from tebi_books_transformers.transform_exact import build_exact_csv

# --- Page config / assets ---
ASSETS = Path(__file__).parent / "assets"
_icon = ASSETS / "IBEOlogo.png"
page_icon = str(_icon) if _icon.is_file() else None
st.set_page_config(page_title="IBEO — Tebi → Exact (beta)", page_icon=page_icon, layout="wide")

def _find_asset(*names: str):
    for n in names:
        p = ASSETS / n
        if p.is_file():
            return str(p)
    return None
def safe_image(names, **kwargs):
    path = _find_asset(*names) if isinstance(names, (list, tuple)) else _find_asset(names)
    if path: st.image(path, **kwargs)

# --- Google OAuth (@ibeo.nl only) ---
CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET")
AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REDIRECT_URI = st.secrets.get("REDIRECT_URI", "http://localhost:8501")
oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_ENDPOINT, TOKEN_ENDPOINT, TOKEN_ENDPOINT)

def require_google_login():
    if "user" in st.session_state: return st.session_state["user"]
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error("Google OAuth not configured."); st.stop()
    st.title("🔐 Sign in with Google")
    result = oauth2.authorize_button(
        name="Sign in with Google",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google-exact",
        extras_params={"prompt":"consent","access_type":"offline","hd":"ibeo.nl"},
        use_container_width=True,
        pkce="S256",
    )
    if result:
        payload = id_token.verify_oauth2_token(result["token"]["id_token"], grequests.Request(), CLIENT_ID)
        email = payload.get("email"); hd = payload.get("hd"); verified = payload.get("email_verified", False)
        ok = verified and ((hd=="ibeo.nl") or (isinstance(email,str) and email.split("@")[-1].lower()=="ibeo.nl"))
        if not ok: st.error("Access restricted to @ibeo.nl accounts."); st.stop()
        st.session_state["user"] = {"email": email, "name": payload.get("name")}
        st.rerun()
    st.stop()

user = require_google_login()

# Header
with st.container():
    c1,c2,c3 = st.columns([1,3,1])
    with c1: safe_image(["IBEOlogo.png","IBEO_logo.png","ibeo_logo.png"], width=150)
    with c2:
        st.markdown("<div style='padding-top:6px;'><h2 style='margin:0'>Tebi → Exact (beta)</h2>"
                    "<p style='margin:0;color:#274c4d;'>Work-in-progress — won’t affect the live Twinfield app</p></div>", unsafe_allow_html=True)
    with c3: safe_image(["Exact_logo_red.png","Exact logo.png","Exact.png"], width=120)
st.divider()

with st.sidebar:
    st.markdown(f"**Signed in as:** {user.get('email','')}")
    if st.button("Log out"): st.session_state.pop("user", None); st.rerun()

# --- Session defaults (Exact beta) ---
defaults = {
    "step": 1, "df": None, "missing_accounts": [], "mapping_dict": {},
    "admin_code": "DEMO1", "currency": "EUR", "use_kpl": False, "kpl_code": "",
    "diff_ledger": "9899"
}
for k,v in defaults.items():
    if k not in st.session_state: st.session_state[k]=v

def next_step(): st.session_state.step += 1
def prev_step(): st.session_state.step = max(1, st.session_state.step-1)
def format_date_for_filename(d):
    try: return pd.to_datetime(d).date().strftime("%Y-%m-%d")
    except Exception: return "unknown"
def build_filename(admin_code, df):
    if "Date" in df.columns:
        ds = pd.to_datetime(df["Date"], errors="coerce").dropna()
        if not ds.empty: start,end = format_date_for_filename(ds.min()), format_date_for_filename(ds.max())
        else: start=end="unknown"
    else: start=end="unknown"
    return f"Tebi EXact import {admin_code} {start} - {end}.csv"

st.title("Exact — Step-by-step (beta)")
st.caption("Select → Upload → Fill info → Map & Run → Download CSV (placeholder schema, to be aligned with your Exact import).")

# Progress
with st.sidebar:
    st.markdown("### Progress")
    for i,label in enumerate(["1. Upload file","2. Fill info","3. Map & Run"], start=1):
        mark = "✅" if st.session_state.step > i else ""
        st.markdown(f"{label} {mark}")
    if st.session_state.step>1: st.button("← Back", on_click=prev_step, use_container_width=True)

# Step 1 (Upload)
if st.session_state.step == 1:
    st.header("Step 1 — Upload Tebi export (CSV/XLSX)")
    up = st.file_uploader("Upload file", type=["csv","xlsx","xls"])
    if up:
        with st.spinner("Reading…"):
            df,_ = load_file(up)
            st.session_state.df = df
        st.success("File loaded."); st.dataframe(st.session_state.df.head(50), use_container_width=True)
    st.button("Next →", on_click=next_step, type="primary", disabled=st.session_state.df is None)

# Step 2 (Info)
elif st.session_state.step == 2:
    st.header("Step 2 — Fill in information")
    c1,c2,c3 = st.columns(3)
    with c1: st.session_state.admin_code = st.text_input("Exact Administration", value=st.session_state.admin_code)
    with c2: st.session_state.currency = st.text_input("Currency", value=st.session_state.currency)
    with c3: st.session_state.diff_ledger = st.text_input("Differences ledger (GL)", value=st.session_state.diff_ledger)

    st.markdown("#### Cost center (KPL)")
    use_kpl_choice = st.radio("Use Cost center (KPL)?", ["No","Yes"], index=0 if not st.session_state.use_kpl else 1, horizontal=True)
    st.session_state.use_kpl = (use_kpl_choice=="Yes")
    if st.session_state.use_kpl:
        st.session_state.kpl_code = st.text_input("Cost center (KPL) code", value=st.session_state.kpl_code)
    st.button("Next →", on_click=next_step, type="primary")

# Step 3 (Map & Run)
elif st.session_state.step == 3:
    st.header("Step 3 — Map missing GL & build CSV")
    df = st.session_state.df.copy()

    if "Account Mapped" in df.columns:
        need = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip()=="")
    else:
        df["Account Mapped"] = ""; need = df["Account Mapped"]==""  # all need mapping

    missing = sorted(set(df.loc[need, "Account"].astype(str)))
    st.info(f"Missing mappings: {len(missing)}")

    rows = [{"Account":a, "Mapped GL": st.session_state.mapping_dict.get(a,"")} for a in missing]
    map_df = pd.DataFrame(rows)
    edited = st.data_editor(map_df, num_rows="dynamic", use_container_width=True, key="map_editor_exact")

    if st.button("Save mappings & Build CSV (beta)"):
        for _,r in edited.iterrows():
            a=str(r.get("Account","")).strip(); g=str(r.get("Mapped GL","")).strip()
            if a and g: st.session_state.mapping_dict[a]=g

        # Apply mappings
        for a,g in st.session_state.mapping_dict.items():
            mask = df["Account"].astype(str)==a
            need = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip()=="")
            df.loc[mask & need, "Account Mapped"]=g

        # Re-check
        need_mask = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip()=="")
        still = sorted(set(df.loc[need_mask, "Account"].astype(str)))
        if still:
            st.warning(f"Still missing {len(still)} mappings. Fill the rest and click again.")
        else:
            # Build placeholder CSV for Exact experiments
            kpl = (st.session_state.kpl_code.strip() if st.session_state.use_kpl else None)
            csv_bytes = build_exact_csv(
                df,
                admin_code=st.session_state.admin_code,
                differences_ledger=st.session_state.diff_ledger,
                currency=st.session_state.currency,
                cost_center_code=kpl
            )
            st.success("CSV built (beta). Download below.")
            st.download_button(
                "Download Exact CSV (beta)",
                data=csv_bytes,
                file_name=build_filename(st.session_state.admin_code, df),
                mime="text/csv",
            )

# Footer
st.markdown(
    "<div style='text-align:center;opacity:0.75;padding-top:24px;'>"
    "Built by <b>IBEO</b> — hospitality accounting made friendly."
    "</div>",
    unsafe_allow_html=True
)
