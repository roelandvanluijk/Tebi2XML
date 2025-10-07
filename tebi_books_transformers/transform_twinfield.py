from xml.etree.ElementTree import Element, SubElement
import pandas as pd
from decimal import Decimal, ROUND_HALF_UP
from .utils import to_float

def _gl(code: str) -> str:
    """Sanitize a GL code so Twinfield doesn't see floats like '4040.0'."""
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except Exception:
        return s  # fallback to given string

def _q2(x) -> Decimal:
    """Quantize to 2 decimals, HALF_UP (e.g., 0.005 -> 0.01)."""
    return Decimal(x).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

def _to_dec(x) -> Decimal:
    val = to_float(x)
    if val is None:
        return Decimal("0.00")
    try:
        return Decimal(str(val))
    except Exception:
        return Decimal("0.00")

def build_twinfield_xml(
    df,
    admin_code,
    journal_code,
    diff_ledger,
    currency='EUR',
    destiny='concept',
    cost_center_code=None,
    round_tolerance=Decimal("0.05"),   # only auto-balance if difference ≤ 5 cents
):
    # Ensure numerics present
    if "Amount_num" not in df.columns and "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
    if "TaxAmount_num" not in df.columns:
        if "Tax Amount" in df.columns:
            df["TaxAmount_num"] = df["Tax Amount"].apply(to_float)
        else:
            df["TaxAmount_num"] = None

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce").dt.date
    txs = Element("transactions")

    # Group per day
    for day, g in df.groupby("Date"):
        if pd.isna(day):
            continue

        t = SubElement(
            txs, "transaction",
            destiny=str(destiny),
            autobalancevat="true",
            raisewarning="false",
        )
        header = SubElement(t, "header")
        SubElement(header, "office").text   = str(admin_code)
        SubElement(header, "code").text     = str(journal_code)
        SubElement(header, "date").text     = pd.to_datetime(day).strftime("%Y%m%d")
        SubElement(header, "currency").text = currency

        lines = SubElement(t, "lines")
        total_debits  = Decimal("0.00")
        total_credits = Decimal("0.00")

        for _, row in g.iterrows():
            gl = _gl(row.get("Account Mapped", ""))
            if not gl or str(gl).lower() == "nan":
                # skip unmapped
                continue

            # Raw inputs as Decimals
            amount_dec = _to_dec(row.get("Amount_num", 0.0))
            tax_amt_dec = None
            if "TaxAmount_num" in row and row["TaxAmount_num"] is not None and not pd.isna(row["TaxAmount_num"]):
                tax_amt_dec = _to_dec(row["TaxAmount_num"])

            vatcode = (row.get("Tax Code Mapped") or "").strip()
            desc    = str(row.get("Account", ""))[:40]

            if amount_dec == 0:
                continue

            is_credit   = amount_dec > 0  # Positive = CREDIT (revenue), Negative = DEBIT (payments/receivables)
            debitcredit = "credit" if is_credit else "debit"

            # Compute NET and VAT per line
            if vatcode and tax_amt_dec is not None:
                # We have an explicit VAT amount -> treat Amount as GROSS and derive NET
                net = _q2(abs(amount_dec) - abs(tax_amt_dec))
                vat = _q2(abs(tax_amt_dec))
                if net < 0:
                    # Guard against pathological rounding – never let NET go negative
                    net = Decimal("0.00")
            elif vatcode:
                # No explicit VAT amount; if there's a Tax Percentage, Amount is likely NET
                rate = row.get("Tax Percentage")
                rate_f = to_float(rate) if rate is not None else None
                if rate_f is not None:
                    net = _q2(abs(amount_dec))
                    vat = _q2(abs(amount_dec) * Decimal(str(rate_f)) / Decimal("100"))
                else:
                    # VAT code but no numbers -> treat as net with 0 VAT
                    net = _q2(abs(amount_dec))
                    vat = None
            else:
                # No VAT on this line
                net = _q2(abs(amount_dec))
                vat = None

            # Build line
            line = SubElement(lines, "line", type="detail")
            SubElement(line, "dim1").text = gl
            if cost_center_code:
                SubElement(line, "dim2").text = str(cost_center_code).strip()
            SubElement(line, "debitcredit").text = debitcredit
            SubElement(line, "value").text = f"{net:.2f}"
            if vatcode:
                SubElement(line, "vatcode").text = vatcode
                if vat is not None and vat > 0:
                    SubElement(line, "vatvalue").text = f"{vat:.2f}"
            SubElement(line, "description").text = desc

            if debitcredit == "debit":
                total_debits += net
            else:
                total_credits += net

        # Day-level imbalance (due only to rounding ideally)
        imbalance = total_debits - total_credits  # >0 -> need more credits; <0 -> need more debits
        if abs(imbalance) > 0 and abs(imbalance) <= round_tolerance:
            bal = SubElement(lines, "line", type="detail")
            SubElement(bal, "dim1").text = _gl(diff_ledger)
            if cost_center_code:
                SubElement(bal, "dim2").text = str(cost_center_code).strip()
            SubElement(bal, "debitcredit").text = "credit" if imbalance > 0 else "debit"
            SubElement(bal, "value").text = f"{abs(imbalance):.2f}"
            SubElement(bal, "description").text = "Rondingsverschillen TEBI"
        # If abs(imbalance) > round_tolerance, we deliberately do NOT auto-balance:
        # it's a real mapping/data issue that should be corrected at the source.

    return txs
