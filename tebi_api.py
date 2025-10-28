# tebi_api.py
import httpx

def _base_url(env: str) -> str:
    return "https://test.tebi.co" if str(env).lower().startswith("test") else "https://live.tebi.co"

def make_client(token: str, env: str = "live") -> httpx.Client:
    return httpx.Client(
        base_url=_base_url(env),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )

def fetch_bookkeeping_export(client: httpx.Client, date_from: str, date_to: str, office_id: str):
    # TODO: replace path/param names with the exact ones from the OpenAPI you see in the browser
    path = "/api/external/bookkeeping/export"
    params = {"startDate": date_from, "endDate": date_to, "office": office_id}
    r = client.get(path, params=params)
    r.raise_for_status()
    return r.content  # CSV bytes (or JSON; adapt in app.py if needed)
