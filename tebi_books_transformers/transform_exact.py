# tebi_books_transformers/transform_exact.py
import pandas as pd
from io import BytesIO
from decimal import Decimal
from .utils import to_float

def _gl(code):
    """Clean GL code (no .0 suffixes)"""
    s = str(code).strip()
    try:
        return str(int(float(s)))
    except Exception:
        return s

def _to_dec(v):
    """Convert to Decimal for precise rounding calculations"""
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal("0.00")

def _q2(d):
    """Quantize to 2 decimal places"""
    return d.quantize(Decimal("0.01"))

def build_exact_csv(df, admin_code, journal_code, differences_ledger, currency="EUR", cost_center_code=None, journal_type="KAS", round_tolerance=Decimal("0.05")):
    """
    Build Exact Online import CSV in Dutch format for KAS (cash) or MEMORIAAL (general journal).
    Based on official Exact Online templates for revenue import.

    Args:
        df: DataFrame with Tebi data
        admin_code: Exact administration code
        journal_code: Dagboek code (e.g., "10" for KAS)
        differences_ledger: GL account for rounding differences
        currency: Currency code (default EUR)
        cost_center_code: Optional cost center (Kostenplaats) code
        journal_type: "KAS" or "MEMORIAAL"
    """
    # Ensure numeric columns exist
    if "Amount_num" not in df.columns and "Amount" in df.columns:
        df["Amount_num"] = df["Amount"].apply(to_float)
    if "TaxAmount_num" not in df.columns and "Tax Amount" in df.columns:
        df["TaxAmount_num"] = df["Tax Amount"].apply(to_float)

    # Parse dates - use 'mixed' format to handle both ISO and European dates correctly
    df["Date"] = pd.to_datetime(df["Date"], format='mixed', errors="coerce")

    # Dutch column names matching Exact Online templates
    dutch_columns = [
        "Dagboek: Code",          # Journal code
        "Boekjaar",               # Fiscal year
        "Periode",                # Period
        "Boekstuknummer",         # Document number
        "Valuta",                 # Currency
    ]

    if journal_type == "KAS":
        dutch_columns.append("Beginsaldo")  # Opening balance (KAS only)
        dutch_columns.append("Datum")       # Date
    else:
        dutch_columns.append("Wisselkoers")  # Exchange rate (MEMORIAAL)
        dutch_columns.append("Boekdatum")    # Booking date

    dutch_columns.extend([
        "Grootboekrekening",      # GL account
        "Omschrijving",           # Description
        "Onze ref.",              # Our reference
        "Bedrag",                 # Amount
        "Aantal",                 # Quantity
        "BTW-code",               # VAT code
        "BTW-percentage",         # VAT percentage
        "BTW-bedrag",             # VAT amount
        "Opmerkingen",            # Notes
        "Project",                # Project
        "Kostenplaats: Code",     # Cost center code
        "Kostenplaats: Omschrijving",  # Cost center description
        "Kostendrager: Code",     # Cost unit code
        "Kostendrager: Omschrijving",  # Cost unit description
        "Code",                   # Account code (relation)
        "Naam"                    # Account name (relation)
    ])

    if journal_type != "KAS":
        # MEMORIAAL needs exchange rate at this position instead of opening balance
        dutch_columns.insert(5, "Wisselkoers")
        dutch_columns.remove("Wisselkoers")  # Remove duplicate

    out_rows = []

    # Group by date to create document numbers and balance per day
    for date_val, group in df.groupby(df["Date"].dt.date):
        if pd.isna(date_val):
            continue

        # Generate document number from date
        date_obj = pd.to_datetime(date_val)
        fiscal_year = date_obj.year
        period = date_obj.month
        doc_number = date_obj.strftime("%y%m%d01")  # Format: YYMMDD01

        # Calculate opening balance for KAS (sum of all amounts for the day)
        opening_balance = 0.0
        if journal_type == "KAS":
            opening_balance = 0.0  # Typically 0, could be calculated if needed

        # Track balance for this day's journal entry
        day_total = Decimal("0.00")
        day_rows = []

        for _, r in group.iterrows():
            gl = _gl(r.get("Account Mapped", ""))
            if not gl or gl.lower() == "nan":
                continue

            amount = r.get("Amount_num")
            if pd.isna(amount) or float(amount) == 0:
                continue

            # Convert to Decimal for precise calculations
            amount_dec = _to_dec(amount)
            day_total += amount_dec

            # Get VAT info
            vat_code = str(r.get("Tax Code Mapped", "")).strip() if pd.notna(r.get("Tax Code Mapped")) else ""
            vat_amount = r.get("TaxAmount_num")
            vat_amount_str = f"{abs(float(vat_amount)):.2f}" if pd.notna(vat_amount) and vat_amount != 0 else ""
            vat_percentage = ""  # Exact Online calculates this from VAT code

            # Description from Account column
            description = str(r.get("Account", ""))[:60] if pd.notna(r.get("Account")) else ""

            # Build row according to Dutch template
            row = {
                "Dagboek: Code": str(journal_code),
                "Boekjaar": str(fiscal_year),
                "Periode": str(period),
                "Boekstuknummer": doc_number,
                "Valuta": currency,
            }

            if journal_type == "KAS":
                row["Beginsaldo"] = f"{opening_balance:.2f}" if opening_balance != 0 else ""
                row["Datum"] = date_obj.strftime("%d-%m-%Y")
            else:
                row["Wisselkoers"] = ""  # Empty for base currency
                row["Boekdatum"] = date_obj.strftime("%d-%m-%Y")

            row.update({
                "Grootboekrekening": gl,
                "Omschrijving": description,
                "Onze ref.": doc_number,
                "Bedrag": f"{float(amount):.2f}",
                "Aantal": "",
                "BTW-code": vat_code,
                "BTW-percentage": vat_percentage,
                "BTW-bedrag": vat_amount_str,
                "Opmerkingen": "",
                "Project": "",
                "Kostenplaats: Code": str(cost_center_code) if cost_center_code else "",
                "Kostenplaats: Omschrijving": "",
                "Kostendrager: Code": "",
                "Kostendrager: Omschrijving": "",
                "Code": "",  # Relation code (optional)
                "Naam": ""   # Relation name (optional)
            })

            day_rows.append(row)

        # Check if this day's entries balance, add rounding correction if needed
        if abs(day_total) > 0 and abs(day_total) <= round_tolerance:
            # Add balancing line to differences ledger
            balance_row = {
                "Dagboek: Code": str(journal_code),
                "Boekjaar": str(fiscal_year),
                "Periode": str(period),
                "Boekstuknummer": doc_number,
                "Valuta": currency,
            }

            if journal_type == "KAS":
                balance_row["Beginsaldo"] = ""
                balance_row["Datum"] = date_obj.strftime("%d-%m-%Y")
            else:
                balance_row["Wisselkoers"] = ""
                balance_row["Boekdatum"] = date_obj.strftime("%d-%m-%Y")

            # Add balancing amount (opposite sign to balance to zero)
            balance_amount = -day_total

            balance_row.update({
                "Grootboekrekening": _gl(differences_ledger),
                "Omschrijving": "Rondingsverschillen TEBI",
                "Onze ref.": doc_number,
                "Bedrag": f"{float(balance_amount):.2f}",
                "Aantal": "",
                "BTW-code": "",
                "BTW-percentage": "",
                "BTW-bedrag": "",
                "Opmerkingen": "Auto-balancing",
                "Project": "",
                "Kostenplaats: Code": str(cost_center_code) if cost_center_code else "",
                "Kostenplaats: Omschrijving": "",
                "Kostendrager: Code": "",
                "Kostendrager: Omschrijving": "",
                "Code": "",
                "Naam": ""
            })

            day_rows.append(balance_row)

        # Add all rows for this day to output
        out_rows.extend(day_rows)

    # Create DataFrame with proper column order
    out_df = pd.DataFrame(out_rows, columns=dutch_columns)

    # Write to CSV
    mem = BytesIO()
    out_df.to_csv(mem, index=False, encoding="utf-8")
    mem.seek(0)
    return mem.getvalue()
