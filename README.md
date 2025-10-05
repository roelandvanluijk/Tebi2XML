# Tebi → Bookkeeping (Twinfield) — Online Tool with Google Workspace Login

A step-by-step Streamlit app to transform **Tebi** exports into **Twinfield** XML (posted as **concept**).  
Includes:
- **Google login restricted to @ibeo.nl** (Google Workspace)
- Wizard flow: Select → Upload → Fill info → Run → Map missing GL → Create XML
- Optional **KPL (Cost center)** stored to `<dim2>`
- **GL code sanitizer** (prevents `4040.0`)
- Correct **signs** (revenue = CREDIT, payments/AR = DEBIT) and day-level **balancing line**
- Filename: `Tebi import [ADMIN] [YYYY-MM-DD] - [YYYY-MM-DD].xml`

---

## 1) Local run (Windows/Mac)
```bash
pip install -r requirements.txt
streamlit run app.py
```

> Tip (Windows): create and activate a virtual environment first
> ```bat
> python -m venv .venv
> .\.venv\Scriptsctivate
> pip install -r requirements.txt
> streamlit run app.py
> ```

---

## 2) Google Cloud setup (OAuth)
1. In the Google Cloud Console (same Workspace as `@ibeo.nl`), create an **OAuth consent screen**.  
   - **User type**: *Internal* (recommended) → auto-restricts to Workspace users.
2. Create **OAuth 2.0 Client ID (Web application)**:
   - Authorized redirect URI (local): `http://localhost:8501`
   - When deployed, add your hosted Streamlit URL too (e.g. `https://your-app.streamlit.app`).
3. Copy client ID/secret into `.streamlit/secrets.toml`:
   ```toml
   GOOGLE_CLIENT_ID = "xxx.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET = "xxx"
   REDIRECT_URI = "http://localhost:8501"
   ```

---

## 3) Deploy options
- **Streamlit Community Cloud (free)** → push this folder to GitHub, deploy with entrypoint `app.py`.  
- **Your own server / Docker** → run `streamlit run app.py` behind Nginx/Caddy.

> On any hosting, set the **secrets** for your app (client ID/secret + redirect URL).

---

## 4) Usage flow
1. **Google Sign-in** (only `@ibeo.nl` allowed).  
2. **Step 1**: select accounting software (Twinfield, Exact coming soon).  
3. **Step 2**: upload Tebi CSV or XLSX (your macro output also works).  
4. **Step 3**: fill Admin code, Journal, Differences ledger, Currency, and optionally **KPL**.  
5. **Step 4**: run checks; if mappings missing go to Step 5.  
6. **Step 5**: type missing GLs and click one button to **Save + Build XML**.  
7. Download the XML and import into Twinfield. Posts as **concept**.

---

## 5) Notes
- VAT lines are supported via `vatcode` and `vatvalue` if present in your data.  
- Day-level balancing line goes to your **Differences ledger**.  
- Cost center (KPL) writes to `<dim2>` on every line (including balancing).  
- If you want KPL only on certain lines, that can be added later.
