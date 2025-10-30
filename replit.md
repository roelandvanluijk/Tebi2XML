# Tebi → Bookkeeping (Twinfield) — Streamlit App

## Overview
A Streamlit web application that transforms Tebi exports into Twinfield XML format (posted as concept). Features Google Workspace login restricted to @ibeo.nl domain.

## Purpose
- Import Tebi exports (CSV/XLSX files)
- Map accounts & VAT codes
- Fix rounding differences
- Generate Twinfield XML files for import (posted as concept)

## Current State
✅ Fully configured and running in Replit environment
- Streamlit app running on port 5000
- Google OAuth authentication setup (requires configuration)
- Deployment configured for autoscale

## Recent Changes (October 30, 2025)
- Imported GitHub repository and configured for Replit
- Installed Python 3.11 and all dependencies
- Configured Streamlit to run on 0.0.0.0:5000 with CORS disabled for Replit proxy
- Set up workflow for Streamlit app
- Configured deployment settings (autoscale)
- Created .gitignore for Python project
- Removed Tebi API functionality (no open API available from Tebi)

## Project Architecture

### Structure
```
tebi_books_transformers/    # Core transformation logic
  - io_reader.py            # File reading utilities
  - transform_twinfield.py  # Twinfield XML generation
  - transform_exact.py      # Exact (KAS) transformation (future)
  - export_xml.py           # XML export utilities
  - utils.py                # Helper functions
app.py                      # Main Streamlit application
app_exact.py                # Exact-specific app (future)
tebi_api.py                 # Tebi API client
assets/                     # Logo images
.streamlit/
  - config.toml             # Streamlit configuration (port 5000)
  - secrets.toml            # OAuth credentials (template)
```

### Key Technologies
- **Streamlit 1.37.1**: Web framework
- **pandas 2.2.3**: Data processing
- **streamlit-oauth 0.1.7**: Google OAuth authentication
- **google-auth**: Google authentication library
- **openpyxl**: Excel file support

### Authentication
- Google OAuth 2.0 with @ibeo.nl domain restriction
- Requires Google Cloud Console OAuth client setup
- Credentials stored in .streamlit/secrets.toml

## Setup Instructions

### Google OAuth Setup
1. Create OAuth 2.0 Client ID in Google Cloud Console
2. Set authorized redirect URI to your Replit URL (e.g., `https://your-repl.repl.co`)
3. Update `.streamlit/secrets.toml` with:
   ```toml
   GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET = "your-client-secret"
   REDIRECT_URI = "https://your-repl-name.repl.co"
   ```


## Usage Flow
1. Sign in with Google (@ibeo.nl only)
2. Select accounting software (Twinfield)
3. Upload Tebi CSV/XLSX file
4. Fill in admin details (admin code, journal, KPL, etc.)
5. Run checks and map missing GL codes
6. Download Twinfield XML file
7. Import into Twinfield (posts as concept)

## Features
- Google Workspace login restricted to @ibeo.nl
- Wizard-style flow with step-by-step guidance
- Optional KPL (Cost center) support stored to `<dim2>`
- GL code sanitizer (prevents issues like "4040.0")
- Correct debit/credit signs and day-level balancing
- VAT lines support via vatcode and vatvalue
- Rounding difference handling

## Deployment
- **Type**: Autoscale (stateless web app)
- **Port**: 5000 (required for Replit)
- **Configuration**: Streamlit configured for Replit proxy (CORS disabled, all hosts allowed)

## Important Notes
- The app processes files in memory and doesn't store data server-side
- OAuth secrets must be configured before first use
- The app requires valid Google credentials to access
- XML files are posted as "concept" in Twinfield for review before finalizing
