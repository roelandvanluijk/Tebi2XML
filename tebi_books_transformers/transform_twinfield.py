from xml.etree.ElementTree import Element, SubElement
import pandas as pd
from .utils import to_float

def _gl(code):
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except Exception:
        return s

def build_twinfield_xml(df, admin_code, journal_code, diff_ledger,
                        currency='EUR', destiny='concept', cost_center_code=None):
    # Ensure numerics
    if "Amount_num" not in df.columns and "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
    if "TaxAmount_num" not in df.columns:
        if "Tax Amount" in df.columns:
            df["TaxAmount_num"] = df["Tax Amount"].apply(to_float)
        else:
            df["TaxAmount_num"] = 0.0

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    txs = Element("transactions")

    for day, g in df.groupby("Date"):
        if pd.isna(day):
            continue

        t = SubElement(txs, "transaction", destiny=str(destiny),
                       autobalancevat="true", raisewarning="false")
        header = SubElement(t, "header")
        SubElement(header, "office").text = str(admin_code)
        SubElement(header, "code").text = str(journal_code)
        SubElement(header, "date").text = pd.to_datetime(day).strftime("%Y%m%d")
        SubElement(header, "currency").text = currency

        lines = SubElement(t, "lines")
        total_debits = 0.0
        total_credits = 0.0

        for _, row in g.iterrows():
            gl = _gl(row.get("Account Mapped", ""))
            if not gl or str(gl).lower() == 'nan':
                continue

            gross = to_float(row.get("Amount_num", 0.0))
            vat   = to_float(row.get("TaxAmount_num", 0.0))
            vatcode = (row.get("Tax Code Mapped") or "")
            desc = str(row.get("Account", ""))[:40]

            if gross == 0.0:
                continue

            # Sign: positive -> credit (revenue), negative -> debit (payments/receivable)
            debitcredit = "credit" if gross > 0 else "debit"

            # If we send a vatcode, <value> must be NET and <vatvalue> the VAT
            has_vat = isinstance(vatcode, str) and vatcode.strip() != ""

            if has_vat and vat != 0:
                base_value = abs(gross - vat)   # NET
                vat_value  = abs(vat)
            else:
                base_value = abs(gross)         # no VAT on this line
                vat_value  = None

            line = SubElement(lines, "line", type="detail")
            SubElement(line, "dim1").text = gl
            if cost_center_code:
                SubElement(line, "dim2").text = str(cost_center_code).strip()
            SubElement(line, "debitcredit").text = debitcredit
            SubElement(line, "value").text = f"{base_value:.2f}"
            if has_vat and vat_value is not None:
                SubElement(line, "vatcode").text = vatcode.strip()
                SubElement(line, "vatvalue").text = f"{vat_value:.2f}"
            SubElement(line, "description").text = desc

            if debitcredit == "debit":
                total_debits += base_value
            else:
                total_credits += base_value

        # Add a balancing line only for real residual rounding
        imbalance = total_debits - total_credits  # >0 -> need more credits; <0 -> need more debits
        tol = 0.02
        if abs(imbalance) > tol:
            bal = SubElement(lines, "line", type="detail")
            SubElement(bal, "dim1").text = _gl(diff_ledger)
            if cost_center_code:
                SubElement(bal, "dim2").text = str(cost_center_code).strip()
            SubElement(bal, "debitcredit").text = "credit" if imbalance > 0 else "debit"
            SubElement(bal, "value").text = f"{abs(imbalance):.2f}"
            SubElement(bal, "description").text = "Rondingsverschillen TEBI"

    return txs
