# tebi_books_transformers/transform_exact.py
import pandas as pd
from io import BytesIO
from .utils import to_float

def _gl(code):
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except Exception:
        return s

def build_exact_csv(df, admin_code, differences_ledger, currency="EUR", cost_center_code=None):
    """
    Minimal CSV scaffold for Exact import experiments.
    NOTE: This is a placeholder schema. We'll align columns once you confirm the Exact import spec you use.
    """
    # Ensure numeric
    if "Amount_num" not in df.columns and "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
    if "TaxAmount_num" not in df.columns and "Tax Amount" in df.columns:
        df["TaxAmount_num"] = df["Tax Amount"].apply(to_float)

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    out_rows = []

    for _, r in df.iterrows():
        gl = _gl(r.get("Account Mapped", ""))
        if not gl or gl.lower() == "nan":
            continue

        net = r.get("Amount_num")
        if pd.isna(net) or float(net) == 0:
            continue

        # Exact journal-style rows (very generic for now)
        amount = abs(float(net))
        debit = amount if net < 0 else 0.0   # payments/AR negative -> debit
        credit = amount if net > 0 else 0.0  # revenue positive -> credit

        out_rows.append({
            "Date": pd.to_datetime(r["Date"]).strftime("%Y-%m-%d") if pd.notna(r["Date"]) else "",
            "GLAccount": gl,
            "Description": str(r.get("Account", ""))[:60],
            "Debit": f"{debit:.2f}",
            "Credit": f"{credit:.2f}",
            "VATCode": (str(r.get("Tax Code Mapped", "")).strip() or ""),
            "VATAmount": ("" if pd.isna(r.get("TaxAmount_num")) else f"{abs(float(r.get('TaxAmount_num'))):.2f}"),
            "CostCenter": (str(cost_center_code).strip() if cost_center_code else ""),
            "Currency": currency,
            "Admin": admin_code,
        })

    # Write CSV bytes
    out_df = pd.DataFrame(out_rows, columns=[
        "Date","GLAccount","Description","Debit","Credit",
        "VATCode","VATAmount","CostCenter","Currency","Admin"
    ])
    mem = BytesIO()
    out_df.to_csv(mem, index=False, encoding="utf-8")
    mem.seek(0)
    return mem.getvalue()
