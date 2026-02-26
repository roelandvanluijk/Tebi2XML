import os
import json
import io
import streamlit as st
import pandas as pd
from datetime import datetime
from pathlib import Path


from tebi_books_transformers.io_reader import load_file
from tebi_books_transformers.transform_twinfield import build_twinfield_xml
from tebi_books_transformers.transform_exact import build_exact_csv
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

def build_filename(admin_code, df, target="Twinfield"):
    if "Date" in df.columns:
        dates = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True).dropna()
        if not dates.empty:
            start = format_date_for_filename(dates.min())
            end = format_date_for_filename(dates.max())
        else:
            start = end = "unknown"
    else:
        start = end = "unknown"

    ext = ".xml" if target == "Twinfield" else ".csv"
    return f"Tebi import {admin_code} {start} - {end}{ext}"

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
        ["Twinfield", "Exact Online"],
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
    
    is_exact = (st.session_state.target == "Exact Online")
    
    # Common fields for both systems
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        label = "Exact Admin code" if is_exact else "Twinfield Admin code"
        st.session_state.admin_code = st.text_input(label, value=st.session_state.admin_code)
    with c2:
        label = "Dagboek code (KAS)" if is_exact else "Twinfield Journal code"
        help_text = "Journal code for KAS (cash journal), e.g., '10'" if is_exact else None
        st.session_state.journal_code = st.text_input(label, value=st.session_state.journal_code, help=help_text)
    with c3:
        st.session_state.diff_ledger = st.text_input("Differences ledger (GL)", value=st.session_state.diff_ledger)
    with c4:
        st.session_state.currency = st.text_input("Currency", value=st.session_state.currency)

    # Software-specific confirmation
    if is_exact:
        st.checkbox("I confirm a KAS Journal exists in Exact Online", value=True)
    else:
        st.checkbox("I confirm a TEBI Journal exists in Twinfield", value=True)

    # Cost center (KPL) - common for both
    st.markdown("#### Cost center (KPL / Kostenplaats)")
    use_kpl_choice = st.radio("Does this administration use a Cost center (KPL)?", ["No", "Yes"], index=0 if not st.session_state.use_kpl else 1)
    st.session_state.use_kpl = (use_kpl_choice == "Yes")
    if st.session_state.use_kpl:
        help_text = "Kostenplaats code for Exact Online" if is_exact else "This will be written to <dim2> in Twinfield."
        st.session_state.kpl_code = st.text_input("Cost center (KPL) code", value=st.session_state.kpl_code, help=help_text)
        if not st.session_state.kpl_code.strip():
            st.info("Please enter the KPL code. Leave blank only if this admin should not use a cost center.")

    st.button("Next →", on_click=next_step, type="primary")

# --- STEP 4 ---
elif st.session_state.step == 4:
    st.header("Step 4 — Run")
    df = st.session_state.df.copy()
    is_exact = (st.session_state.target == "Exact Online")

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
        # Generate file based on selected software
        if is_exact:
            with st.spinner("Building Exact Online CSV (KAS journal)…"):
                csv_bytes = build_exact_csv(
                    df,
                    admin_code=st.session_state.admin_code,
                    journal_code=st.session_state.journal_code,
                    differences_ledger=st.session_state.diff_ledger,
                    currency=st.session_state.currency,
                    cost_center_code=(st.session_state.kpl_code.strip() if st.session_state.use_kpl else None),
                    journal_type="KAS"
                )
            st.success("CSV built. Download below and import via Exact Online → Financieel → Import.")
            file_name = build_filename(st.session_state.admin_code, df, target="Exact Online")
            st.download_button("Download Exact CSV (KAS)", data=csv_bytes, file_name=file_name, mime="text/csv")
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
            file_name = build_filename(st.session_state.admin_code, df, target="Twinfield")
            st.download_button("Download Twinfield XML", data=xml_bytes, file_name=file_name, mime="application/xml")
    st.button("← Back", on_click=prev_step)

# --- STEP 5 ---
elif st.session_state.step == 5:
    st.header("Step 5 — Map missing ledgers & rerun")
    df = st.session_state.df.copy()
    missing_accounts = st.session_state.missing_accounts
    is_exact = (st.session_state.target == "Exact Online")
    button_label = "Save mappings & Build CSV" if is_exact else "Save mappings & Build XML"

    if not missing_accounts:
        st.info("No missing mappings detected. Go back to Step 4 to run.")

    map_rows = [{"Account": a, "Mapped GL": st.session_state.mapping_dict.get(a, "")} for a in missing_accounts]
    map_df = pd.DataFrame(map_rows)

    st.markdown("#### Add GL (dim1) for each missing source account")
    edited = st.data_editor(map_df, num_rows="dynamic", use_container_width=True, key="map_editor")

    if st.button(button_label):
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
                # Generate file based on selected software
                if is_exact:
                    with st.spinner("Building Exact Online CSV (KAS journal)…"):
                        csv_bytes = build_exact_csv(
                            df,
                            admin_code=st.session_state.admin_code,
                            journal_code=st.session_state.journal_code,
                            differences_ledger=st.session_state.diff_ledger,
                            currency=st.session_state.currency,
                            cost_center_code=(st.session_state.kpl_code.strip() if st.session_state.use_kpl else None),
                            journal_type="KAS"
                        )
                    st.success("CSV built. Download below and import via Exact Online → Financieel → Import.")
                    file_name = build_filename(st.session_state.admin_code, df, target="Exact Online")
                    st.download_button("Download Exact CSV (KAS)", data=csv_bytes, file_name=file_name, mime="text/csv")
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
                    file_name = build_filename(st.session_state.admin_code, df, target="Twinfield")
                    st.download_button("Download Twinfield XML", data=xml_bytes, file_name=file_name, mime="application/xml")
    st.button("← Back", on_click=prev_step)

# --- Footer ---
st.markdown(
    "<div style='text-align:center;opacity:0.75;padding-top:24px;'>"
    "Built by <b>IBEO</b> — hospitality accounting made friendly."
    "</div>",
    unsafe_allow_html=True
)
