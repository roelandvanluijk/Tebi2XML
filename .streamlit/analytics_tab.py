# analytics_tab.py (or inside a new "Dashboard (beta)" tab)
import io, json, pandas as pd, streamlit as st
from tebi_api import make_client  # your tiny wrapper
from datetime import date

env = st.selectbox("Environment", ["live","test"])
d1, d2 = st.columns(2)
with d1: start = st.date_input("Start", value=date.today().replace(day=1))
with d2: end   = st.date_input("End", value=date.today())
admin = st.text_input("Office/Admin", value=st.session_state.get("admin_code","DEMO1"))
go = st.button("Fetch from Tebi")

if go:
    token = st.secrets.get("TEBI_API_TOKEN")
    if not token:
        st.error("Missing TEBI_API_TOKEN in secrets.")
    else:
        client = make_client(token, env)
        # 🔁 Replace path/params with the exact ones from https://api.docs.tebi.com/openapi/
        # Example idea: /api/external/reports/sales?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&office=DEMO1
        r = client.get("/api/external/reports/sales", params={
            "startDate": start.isoformat(), "endDate": end.isoformat(), "office": admin
        })
        r.raise_for_status()

        # If CSV:
        try:
            df = pd.read_csv(io.BytesIO(r.content))
        except Exception:
            # If JSON:
            df = pd.json_normalize(r.json())

        # ---- KPIs ----
        # Expect columns like: Date, SaleId, Gross, Net, Products[], Qty, etc. (names vary by endpoint)
        # Tweak column names once you confirm the payload.
        close_count = df["SaleId"].nunique() if "SaleId" in df.columns else len(df)
        revenue = df.get("Revenue", df.get("Net", df.get("Gross", 0))).sum()
        avg_spend = (revenue / close_count) if close_count else 0

        k1, k2, k3 = st.columns(3)
        k1.metric("Total revenue", f"{revenue:,.2f}")
        k2.metric("Closed sales", f"{close_count:,}")
        k3.metric("Average spend", f"{avg_spend:,.2f}")

        # ---- Top products ----
        # Example assumes item-level rows with columns ProductName and LineTotal
        if {"ProductName","LineTotal"} <= set(df.columns):
            top = (df.groupby("ProductName", as_index=False)["LineTotal"]
                     .sum().sort_values("LineTotal", ascending=False).head(15))
            st.subheader("Top products")
            st.dataframe(top, use_container_width=True)

        # ---- Busiest hours ----
        # Example assumes a timestamp column "ClosedAt"
        if "ClosedAt" in df.columns:
            tmp = df.copy()
            tmp["ClosedAt"] = pd.to_datetime(tmp["ClosedAt"], errors="coerce")
            tmp = tmp.dropna(subset=["ClosedAt"])
            tmp["hour"] = tmp["ClosedAt"].dt.tz_convert("Europe/Amsterdam").dt.hour if tmp["ClosedAt"].dt.tz is not None else tmp["ClosedAt"].dt.hour
            busy = tmp.groupby("hour", as_index=False).size().rename(columns={"size":"Sales"})
            st.subheader("Busiest hours")
            st.bar_chart(busy.set_index("hour"))

        st.download_button("Export raw (CSV)", data=df.to_csv(index=False), file_name="tebi_analytics.csv", mime="text/csv")
