import pandas as pd
from .utils import to_float

REQUIRED_TEBI_COLS = [
    "Date", "Account", "Account Mapped", "Amount",
    "Tax Amount", "Tax Code Mapped", "Tax Percentage"
]

XLS_MAP = {
    "Datum": "Date",
    "Omschrijving": "Account",
    "Grtboekrek.": "Account Mapped",
    "Bedrag": "Amount",
    "Btwcode": "Tax Code Mapped",
}
DC_COL = "DebitCredit"  # debit/credit from macro

VAT_CODE_TO_PERC = {"VH": 21.0, "VL": 9.0}

def _read_csv_autodelim_str(text):
    from io import StringIO
    for sep in [';', ',', '|', '\t']:
        try:
            df = pd.read_csv(StringIO(text), sep=sep, engine='python')
            if df.shape[1] >= 4:
                return df
        except Exception:
            continue
    return pd.read_csv(StringIO(text), engine='python')

def _normalize_tebi_csv(df):
    df = df.rename(columns=lambda c: str(c).strip())
    for col in ["Amount", "Tax Amount", "Tax Percentage"]:
        if col in df.columns:
            df[col + "_num"] = df[col].apply(to_float)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True).dt.date
    missing = [c for c in REQUIRED_TEBI_COLS if c not in df.columns]
    return df, missing

def _normalize_xls_macro(df):
    df = df.rename(columns={k:v for k,v in XLS_MAP.items() if k in df.columns})
    if "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
        if DC_COL in df.columns:
            df["Amount_num"] = df.apply(lambda r: r["Amount_num"] if str(r.get(DC_COL, '')).lower()=='debit' else -abs(r["Amount_num"]), axis=1)
    if "Tax Percentage" not in df.columns:
        df["Tax Percentage"] = df.get("Tax Code Mapped", "").map(VAT_CODE_TO_PERC)
    df["TaxPerc_num"] = df["Tax Percentage"]
    if "Tax Amount" not in df.columns:
        df["Tax Amount"] = None
    df["TaxAmount_num"] = df.apply(lambda r: (r["Amount_num"] * (float(r["TaxPerc_num"]) / 100.0)) if pd.notna(r.get("TaxPerc_num")) and pd.notna(r.get("Amount_num")) else None, axis=1)
    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", dayfirst=True).dt.date
    return df, []

def load_file(uploaded_file):
    name = uploaded_file.name.lower()
    if name.endswith(".csv"):
        text = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        df = _read_csv_autodelim_str(text)
        return _normalize_tebi_csv(df)
    elif name.endswith(".xlsx") or name.endswith(".xls"):
        df = pd.read_excel(uploaded_file)
        return _normalize_xls_macro(df)
    else:
        text = uploaded_file.getvalue().decode("utf-8", errors="ignore")
        df = _read_csv_autodelim_str(text)
        return _normalize_tebi_csv(df)
