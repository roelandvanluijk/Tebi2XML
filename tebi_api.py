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
    path = path_override or os.environ.get("TEBI_BOOKKEEPING_PATH") or "/api/external/bookkeeping/export"
    params = {"startDate": date_from, "endDate": date_to, "office": office_id}
    r = client.get(path, params=params)
    r.raise_for_status()
    return r.content

def list_accounts(client: httpx.Client):
    """Return [{'id': '...', 'name': '...'}, ...] or [] if none. Update paths when you know the real one."""
    candidates = [
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
                items = data if isinstance(data, list) else (data.get("data") or data.get("items") or [])
                out = []
                for it in items:
                    name = it.get("name") or it.get("label") or it.get("displayName") or it.get("officeName")
                    _id  = it.get("id")   or it.get("office") or it.get("code")        or it.get("officeId")
                    if _id:
                        out.append({"id": str(_id), "name": str(name or _id)})
                if out:
                    return out
        except httpx.HTTPError:
            pass
    return []
