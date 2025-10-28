# tebi_api.py
import os, httpx

def _base_url(env: str) -> str:
    return "https://test.tebi.co" if str(env).lower().startswith("test") else "https://live.tebi.co"

def make_client(token: str, env: str = "live") -> httpx.Client:
    return httpx.Client(
        base_url=_base_url(env),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

def fetch_bookkeeping_export(client: httpx.Client, date_from: str, date_to: str, office_id: str, path_override: str | None = None):
    """
    Returns raw bytes (CSV or JSON) for the bookkeeping export.
    - Set TEBI_BOOKKEEPING_PATH in secrets (or pass path_override) to the exact path from OpenAPI,
      e.g. "/api/external/reports/bookkeeping" or similar.
    """
    path = path_override or os.environ.get("TEBI_BOOKKEEPING_PATH") or "/api/external/bookkeeping/export"
    params = {"startDate": date_from, "endDate": date_to, "office": office_id}
    r = client.get(path, params=params)
    r.raise_for_status()  # will raise for 404/401/etc.
    return r.content

def list_accounts(client: httpx.Client):
    """
    Try to fetch the list of accounts/organizations accessible by this token.
    Returns a list of dicts like: [{"id": "...","name":"..."}, ...] or [] if none.
    NOTE: Replace with the exact endpoint from Tebi OpenAPI when you have it.
    """
    candidates = [
        # <-- put the real one first once you confirm it in OpenAPI
        "/api/external/accounts",
        "/api/external/organizations",
        "/api/external/offices",
        "/api/external/merchants/me/accounts",
    ]
    for path in candidates:
        try:
            r = client.get(path)
            if r.status_code == 200:
                data = r.json()
                # Try to normalize common shapes
                if isinstance(data, list):
                    items = data
                elif isinstance(data, dict):
                    # common patterns: {"data":[...]} or {"items":[...]}
                    items = data.get("data") or data.get("items") or []
                else:
                    items = []

                out = []
                for it in items:
                    # Guess common keys
                    name = it.get("name") or it.get("label") or it.get("displayName") or it.get("officeName")
                    _id  = it.get("id") or it.get("office") or it.get("code") or it.get("officeId")
                    if _id:
                        out.append({"id": str(_id), "name": str(name or _id)})
                if out:
                    return out
        except httpx.HTTPError:
            pass
    return []
