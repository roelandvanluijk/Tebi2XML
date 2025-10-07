# tebi_api.py
import os
import httpx

def _base_url(env: str) -> str:
    # You can change this if the OpenAPI lists a different host/path for the export.
    # Using scheme hosts from the docs:
    # test env:  https://test.tebi.co
    # live env:  https://live.tebi.co
    return "https://test.tebi.co" if env.lower().startswith("test") else "https://live.tebi.co"

def make_client(token: str, env: str = "live") -> httpx.Client:
    return httpx.Client(
        base_url=_base_url(env),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

def fetch_bookkeeping_export(client: httpx.Client, date_from: str, date_to: str, office_id: str):
    """
    Returns bytes/CSV (or JSON) from Tebi's external API for the bookkeeping export.
    NOTE: Replace the path and params below with the exact endpoint & query names
    shown in your Tebi OpenAPI (https://api.docs.tebi.com/openapi/).
    """
    # ↓↓↓ Placeholder path & params — adjust to match the official OpenAPI path
    # For example, it might be something like:
    # /api/external/bookkeeping/export?startDate=YYYY-MM-DD&endDate=YYYY-MM-DD&office=DEMO1
    path = "/api/external/bookkeeping/export"
    params = {"startDate": date_from, "endDate": date_to, "office": office_id}

    r = client.get(path, params=params)
    r.raise_for_status()
    return r.content  # could be CSV or JSON depending on the endpoint
