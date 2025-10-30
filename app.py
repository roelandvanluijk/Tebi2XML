import os
import json
import io
import streamlit as st
import pandas as pd
from datetime import datetime
from streamlit_oauth import OAuth2Component
from google.oauth2 import id_token
from google.auth.transport import requests as grequests
from pathlib import Path


from tebi_books_transformers.io_reader import load_file
from tebi_books_transformers.transform_twinfield import build_twinfield_xml
from tebi_books_transformers.export_xml import xml_to_bytes

# ---------- Assets & page config ----------
ASSETS = Path(__file__).parent / "assets"
_icon = ASSETS / "IBEOlogo.png"
page_icon = str(_icon) if _icon.is_file() else None

# MUST be first Streamlit command (only once)
st.set_page_config(
    page_title="IBEO — Tebi → Twinfield & Exact",
    page_icon=page_icon,
    layout="wide",
)

# Safe image helpers (won't crash if a file is missing)
def _find_asset(*names: str):
    for n in names:
        p = ASSETS / n
        if p.is_file():
            return str(p)
    return None

def safe_image(names, **kwargs):
    path = _find_asset(*names) if isinstance(names, (list, tuple)) else _find_asset(names)
    if path:
        st.image(path, **kwargs)

def show_landing():
    # Top brand strip
    with st.container():
        c1, c2, c3 = st.columns([1,3,1])
        with c1:
            safe_image(["IBEOlogo.png", "IBEO_logo.png", "ibeo_logo.png"], width=140)
        with c2:
            st.markdown(
                "<div style='padding-top:6px;'><h1 style='margin:0'>Tebi → Twinfield & Exact</h1>"
                "<p style='margin:0;color:#274c4d;'>Convert daily revenue exports into clean, importable journals</p></div>",
                unsafe_allow_html=True,
            )
        with c3:
            safe_image(["Tebi_logo.png", "Tebi logo.png", "tebi_logo.png"], width=110)
    st.divider()

    # What this app does
    st.subheader("What this app does")
    st.markdown("""
    - **Imports Tebi exports** (CSV/XLSX files)  
    - **Maps accounts & VAT**, fixes rounding differences  
    - **Builds Twinfield XML** (posted as **concept**) — Exact (KAS) coming soon
    """)

    # Why login
    st.subheader("Why login?")
    st.markdown("""
    - Only **IBEO** colleagues should access these tools  
    - We require **Google sign-in with @ibeo.nl** to keep data secure
    """)

    # Data & privacy
    with st.expander("About your data & privacy", expanded=False):
        st.markdown("""
        - Files are processed **in memory** and not stored on the server  
        - API tokens are kept in **Streamlit Secrets** (server-side)  
        - Output files are generated per session and offered for **download**
        """)

    # Quick how-to
    st.subheader("How it works")
    st.markdown("""
    1. Log in with **@ibeo.nl**  
    2. Choose your accounting software  
    3. Upload a Tebi export (CSV or XLSX)  
    4. Fill in admin details (journal, KPL, etc.)  
    5. Build the file and import in Twinfield / (soon) Exact
    """)


# -------------------------
# Google OAuth login (@ibeo.nl only)
# -------------------------
CLIENT_ID = st.secrets.get("GOOGLE_CLIENT_ID")
CLIENT_SECRET = st.secrets.get("GOOGLE_CLIENT_SECRET")
AUTHORIZE_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
REDIRECT_URI = st.secrets.get("REDIRECT_URI", "http://localhost:8501")

oauth2 = OAuth2Component(CLIENT_ID, CLIENT_SECRET, AUTHORIZE_ENDPOINT, TOKEN_ENDPOINT, TOKEN_ENDPOINT)

def require_google_login():
    # If already logged in, return user info
    if "user" in st.session_state:
        return st.session_state["user"]

    # If OAuth not configured, show a clear error
    if not CLIENT_ID or not CLIENT_SECRET:
        st.error("Google OAuth is not configured. Set GOOGLE_CLIENT_ID/GOOGLE_CLIENT_SECRET in .streamlit/secrets.toml")
        st.stop()

    # PUBLIC landing (info) + Sign-in button
    show_landing()
    st.markdown("### Continue")
    result = oauth2.authorize_button(
        name="Sign in with Google",
        icon="https://www.google.com/favicon.ico",
        redirect_uri=REDIRECT_URI,
        scope="openid email profile",
        key="google",
        extras_params={"prompt": "consent", "access_type": "offline", "hd": "ibeo.nl"},
        use_container_width=True,
        pkce="S256",
    )

    if result:
        token = result["token"]
        idt = token["id_token"]
        payload = id_token.verify_oauth2_token(idt, grequests.Request(), CLIENT_ID)

        email = payload.get("email")
        hd = payload.get("hd")
        email_verified = payload.get("email_verified", False)

        domain_ok = (hd == "ibeo.nl") or (isinstance(email, str) and email.split("@")[-1].lower() == "ibeo.nl")
        if not email_verified or not domain_ok:
            st.error("Access restricted to verified @ibeo.nl Google Workspace accounts.")
            st.stop()

        st.session_state["user"] = {
            "email": email,
            "name": payload.get("name"),
            "picture": payload.get("picture"),
        }
        st.rerun()

    # Don’t render the private app until logged in
    st.stop()


user = require_google_login()

# === Branded header ===
with st.container():
    c1, c2, c3 = st.columns([1,3,1], vertical_alignment="center")
    with c1:
        safe_image(["IBEOlogo.png", "IBEO_logo.png", "ibeo_logo.png"], width=150)
    with c2:
        st.markdown(
            "<div style='padding-top:6px;'><h2 style='margin:0'>Tebi → Twinfield & Exact</h2>"
            "<p style='margin:0;color:#274c4d;'>Built by IBEO — fast, consistent daily revenue imports</p></div>",
            unsafe_allow_html=True,
        )
    with c3:
        safe_image(["Tebi_logo.png", "Tebi logo.png", "tebi_logo.png"], width=110)
st.divider()

with st.sidebar:
    st.markdown(f"**Signed in as:** {user.get('email','')}")
    if st.button("Log out"):
        st.session_state.pop("user", None)
        st.rerun()

# -------------------------
# App session defaults
# -------------------------
defaults = {
    "step": 1,
    "prev_step_num": 1,
    "df": None,
    "missing_accounts": [],
    "mapping_dict": {},       # {source Account -> mapped GL}
    "target": "Twinfield",
    "admin_code": "DEMO1",
    "journal_code": "TEBI",
    "diff_ledger": "9899",
    "currency": "EUR",
    "use_kpl": False,
    "kpl_code": "",
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

def next_step():
    st.session_state.prev_step_num = st.session_state.step
    st.session_state.step += 1

def prev_step():
    st.session_state.prev_step_num = st.session_state.step
    st.session_state.step = max(1, st.session_state.step - 1)

def format_date_for_filename(d):
    if pd.isna(d):
        return "unknown"
    try:
        return pd.to_datetime(d).date().strftime("%Y-%m-%d")
    except Exception:
        return str(d)

def build_filename(admin_code, df):
    if "Date" in df.columns:
        dates = pd.to_datetime(df["Date"], errors="coerce").dropna()
        if not dates.empty:
            start = format_date_for_filename(dates.min())
            end = format_date_for_filename(dates.max())
        else:
            start = end = "unknown"
    else:
        start = end = "unknown"
    return f"Tebi import {admin_code} {start} - {end}.xml"

st.title("Tebi → Bookkeeping — Step-by-step")
st.caption("Select → Upload → Fill info → Run → Map missing GL → Rerun (Twinfield XML posts as concept).")

# --- Sidebar progress ---
with st.sidebar:
    st.markdown("### Progress")
    labels = [
        "1. Select software",
        "2. Upload file",
        "3. Fill info",
        "4. Run",
        "5. Map missing ledgers",
    ]
    for i, label in enumerate(labels, start=1):
        mark = "✅" if st.session_state.step > i else ""
        st.markdown(f"{label} {mark}")
    if st.session_state.step > 1:
        st.button("← Back", on_click=prev_step, use_container_width=True)

# --- STEP 1 ---
if st.session_state.step == 1:
    st.header("Step 1 — Select accounting software")

    lc1, lc2, lc3 = st.columns([1,1,2])
    with lc1:
        # NOTE: Streamlit's st.image doesn't accept height=..., so we use width=...
        safe_image(["Twinfield_logo.png", "twinfield logo.png", "Twinfield.png"], width=120)
    with lc2:
        safe_image(["Exact_logo_red.png", "Exact logo.png", "Exact.png"], width=120)

    st.session_state.target = st.radio(
        "Choose:",
        ["Twinfield", "Exact (coming soon)"],
        index=0,
        horizontal=True,
    )

    st.button("Next →", on_click=next_step, type="primary")

# --- STEP 2 ---
elif st.session_state.step == 2:
    if st.session_state.prev_step_num > 2:
        st.session_state.df = None
        st.session_state.missing_accounts = []
        st.session_state.mapping_dict = {}
        st.session_state.prev_step_num = 2
    
    st.header("Step 2 — Upload data")
    st.markdown("Upload your Tebi export file (CSV or XLSX format)")
    
    if st.session_state.df is not None:
        st.info("✓ File already loaded. Upload a new file to replace it, or click 'Clear' to start fresh.")
        if st.button("Clear uploaded file"):
            st.session_state.df = None
            st.rerun()
    
    up = st.file_uploader("Upload file", type=["csv", "xlsx", "xls"], key="file_upload_step2")
    if up:
        df, _missing = load_file(up)
        st.session_state.df = df
        st.success("File loaded.")
        st.dataframe(df.head(50), use_container_width=True)

    st.button("Next →", on_click=next_step, type="primary", disabled=st.session_state.df is None)


# --- STEP 3 ---
elif st.session_state.step == 3:
    st.header("Step 3 — Fill in information")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.session_state.admin_code = st.text_input("Twinfield Admin code", value=st.session_state.admin_code)
    with c2:
        st.session_state.journal_code = st.text_input("Twinfield Journal code", value=st.session_state.journal_code)
    with c3:
        st.session_state.diff_ledger = st.text_input("Differences ledger (GL)", value=st.session_state.diff_ledger)
    with c4:
        st.session_state.currency = st.text_input("Currency", value=st.session_state.currency)

    st.checkbox("I confirm a TEBI Journal exists in Twinfield", value=True)

    st.markdown("#### Cost center (KPL)")
    use_kpl_choice = st.radio("Does this administration use a Cost center (KPL)?", ["No", "Yes"], index=0 if not st.session_state.use_kpl else 1)
    st.session_state.use_kpl = (use_kpl_choice == "Yes")
    if st.session_state.use_kpl:
        st.session_state.kpl_code = st.text_input("Cost center (KPL) code", value=st.session_state.kpl_code, help="This will be written to <dim2> in Twinfield.")
        if not st.session_state.kpl_code.strip():
            st.info("Please enter the KPL code. Leave blank only if this admin should not use a cost center.")

    st.button("Next →", on_click=next_step, type="primary")

# --- STEP 4 ---
elif st.session_state.step == 4:
    st.header("Step 4 — Run")
    df = st.session_state.df.copy()

    if st.session_state.use_kpl and (not st.session_state.kpl_code.strip()):
        st.error("This admin uses a Cost center, but no KPL code was provided in Step 3.")
        st.button("← Back to Step 3", on_click=prev_step)
        st.stop()

    if "Account Mapped" in df.columns:
        need = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip() == "")
    else:
        df["Account Mapped"] = ""
        need = df["Account Mapped"] == ""

    missing_accounts = sorted(set(df.loc[need, "Account"].astype(str)))
    st.session_state.missing_accounts = missing_accounts

    if missing_accounts:
        st.warning(f"Missing GL mapping for {len(missing_accounts)} source accounts. Proceed to Step 5 to map and rerun.")
        st.button("Go to Step 5 →", on_click=lambda: st.session_state.update(step=5), type="primary")
    else:
        with st.spinner("Building Twinfield XML (concept)…"):
            root = build_twinfield_xml(
                df,
                st.session_state.admin_code,
                st.session_state.journal_code,
                st.session_state.diff_ledger,
                currency=st.session_state.currency,
                destiny="concept",
                cost_center_code=(st.session_state.kpl_code.strip() if st.session_state.use_kpl else None),
            )
            xml_bytes = xml_to_bytes(root)
        st.success("XML built. Download below.")
        file_name = build_filename(st.session_state.admin_code, df)
        st.download_button("Download Twinfield XML", data=xml_bytes, file_name=file_name, mime="application/xml")
    st.button("← Back", on_click=prev_step)

# --- STEP 5 ---
elif st.session_state.step == 5:
    st.header("Step 5 — Map missing ledgers & rerun")
    df = st.session_state.df.copy()
    missing_accounts = st.session_state.missing_accounts

    if not missing_accounts:
        st.info("No missing mappings detected. Go back to Step 4 to run.")

    map_rows = [{"Account": a, "Mapped GL": st.session_state.mapping_dict.get(a, "")} for a in missing_accounts]
    map_df = pd.DataFrame(map_rows)

    st.markdown("#### Add GL (dim1) for each missing source account")
    edited = st.data_editor(map_df, num_rows="dynamic", use_container_width=True, key="map_editor")

    if st.button("Save mappings & Build XML"):
        for _, r in edited.iterrows():
            acc = str(r.get("Account", "")).strip()
            gl = str(r.get("Mapped GL", "")).strip()
            if acc and gl:
                st.session_state.mapping_dict[acc] = gl

        for acc, gl in st.session_state.mapping_dict.items():
            mask = df["Account"].astype(str) == acc
            need = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip() == "")
            df.loc[mask & need, "Account Mapped"] = gl

        st.session_state.df = df
        need_mask = df["Account Mapped"].isna() | (df["Account Mapped"].astype(str).str.strip() == "")
        st.session_state.missing_accounts = sorted(set(df.loc[need_mask, "Account"].astype(str)))

        if st.session_state.missing_accounts:
            st.warning(f"Still missing {len(st.session_state.missing_accounts)} mappings. Add the rest and click the button again.")
        else:
            if st.session_state.use_kpl and (not st.session_state.kpl_code.strip()):
                st.error("This admin uses a Cost center, but no KPL code was provided in Step 3.")
            else:
                with st.spinner("Building Twinfield XML (concept)…"):
                    root = build_twinfield_xml(
                        df,
                        st.session_state.admin_code,
                        st.session_state.journal_code,
                        st.session_state.diff_ledger,
                        currency=st.session_state.currency,
                        destiny="concept",
                        cost_center_code=(st.session_state.kpl_code.strip() if st.session_state.use_kpl else None),
                    )
                    xml_bytes = xml_to_bytes(root)
                st.success("XML built. Download below.")
                file_name = build_filename(st.session_state.admin_code, df)
                st.download_button("Download Twinfield XML", data=xml_bytes, file_name=file_name, mime="application/xml")
    st.button("← Back", on_click=prev_step)

# --- Footer ---
st.markdown(
    "<div style='text-align:center;opacity:0.75;padding-top:24px;'>"
    "Built by <b>IBEO</b> — hospitality accounting made friendly."
    "</div>",
    unsafe_allow_html=True
)
