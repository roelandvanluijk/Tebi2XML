from xml.etree.ElementTree import Element, SubElement
import pandas as pd
from .utils import to_float

def _gl(code):
    # Sanitize a GL code so Twinfield doesn't see floats like '4040.0'.
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except Exception:
        return s  # fallback to given string

def build_twinfield_xml(df, admin_code, journal_code, diff_ledger, currency='EUR', destiny='concept', cost_center_code=None):
    # Ensure numerics
    if "Amount_num" not in df.columns and "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
    if "TaxAmount_num" not in df.columns:
        if "Tax Amount" in df.columns:
            df["TaxAmount_num"] = df["Tax Amount"].apply(to_float)
        else:
            df["TaxAmount_num"] = None

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    txs = Element("transactions")
    # group by day
    for day, g in df.groupby("Date"):
        if pd.isna(day):
            continue
        t = SubElement(txs, "transaction", destiny=str(destiny), autobalancevat="true", raisewarning="false")
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
            if not gl or gl.lower()=='nan':
                continue
            net = row.get("Amount_num")
            vat = row.get("TaxAmount_num")
            vatcode = row.get("Tax Code Mapped")
            desc = str(row.get("Account", ""))[:40]

            if pd.isna(net) or float(net) == 0.0:
                continue

            # Positive = CREDIT (revenue), Negative = DEBIT (payments/receivables)
            debitcredit = "credit" if float(net) > 0 else "debit"
            value_abs = abs(float(net))

            line = SubElement(lines, "line", type="detail")
            SubElement(line, "dim1").text = gl
            if cost_center_code:
                SubElement(line, "dim2").text = str(cost_center_code).strip()
            SubElement(line, "debitcredit").text = debitcredit
            SubElement(line, "value").text = f"{value_abs:.2f}"
            if isinstance(vatcode, str) and vatcode.strip():
                SubElement(line, "vatcode").text = vatcode.strip()
                if vat is not None and not pd.isna(vat):
                    SubElement(line, "vatvalue").text = f"{abs(float(vat)):.2f}"
            SubElement(line, "description").text = desc

            if debitcredit == "debit":
                total_debits += value_abs
            else:
                total_credits += value_abs

        # Add a true balancing line based on debit/credit totals
        imbalance = total_debits - total_credits  # >0 -> need more credits; <0 -> need more debits
        tol = 0.02  # cents-level tolerance
        if abs(imbalance) > tol:
            bal = SubElement(lines, "line", type="detail")
            SubElement(bal, "dim1").text = _gl(diff_ledger)
            if cost_center_code:
                SubElement(bal, "dim2").text = str(cost_center_code).strip()
            if imbalance > 0:
                # Debits > Credits -> add a CREDIT line
                SubElement(bal, "debitcredit").text = "credit"
                SubElement(bal, "value").text = f"{abs(imbalance):.2f}"
            else:
                # Credits > Debits -> add a DEBIT line
                SubElement(bal, "debitcredit").text = "debit"
                SubElement(bal, "value").text = f"{abs(imbalance):.2f}"
            SubElement(bal, "description").text = "Rondingsverschillen TEBI"
    return txs
