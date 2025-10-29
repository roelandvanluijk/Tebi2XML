"""
Tebi API Client
Enhanced with automated export and GitHub commit functionality
"""

import os
import httpx
import json
import csv
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _base_url(env: str) -> str:
    return "https://test.tebi.co" if str(env).lower().startswith("test") else "https://live.tebi.co"


def make_client(token: str, env: str = "live") -> httpx.Client:
    return httpx.Client(
        base_url=_base_url(env),
        headers={"Authorization": f"Bearer {token}"},
        timeout=30.0,
    )


def fetch_bookkeeping_export(
    client: httpx.Client, 
    date_from: str, 
    date_to: str, 
    office_id: str, 
    path_override: str | None = None
):
    """
    Fetch bookkeeping export from Tebi
    
    Args:
        client: httpx client
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        office_id: Office/venue ID
        path_override: Optional custom path
        
    Returns:
        Raw response content (bytes)
    """
    path = path_override or os.environ.get("TEBI_BOOKKEEPING_PATH") or "/api/external/bookkeeping/export"
    params = {"startDate": date_from, "endDate": date_to, "office": office_id}
    
    logger.info(f"Fetching bookkeeping: {date_from} to {date_to} for office {office_id}")
    
    r = client.get(path, params=params)
    r.raise_for_status()
    
    logger.info(f"✅ Fetched {len(r.content)} bytes")
    return r.content


def list_accounts(client: httpx.Client):
    """
    Return list of accounts/offices accessible to this token
    
    Returns:
        [{'id': '...', 'name': '...'}, ...] or [] if none
    """
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
                    logger.info(f"✅ Found {len(out)} accounts via {path}")
                    return out
        except httpx.HTTPError:
            pass
    
    logger.warning("No accounts found")
    return []


# ==================== NEW: AUTO-EXPORT FEATURES ====================

def save_export_to_file(
    content: bytes,
    office_name: str,
    date_from: str,
    date_to: str,
    output_dir: str = "exports",
    format: str = "json"
) -> str:
    """
    Save exported data to file
    
    Args:
        content: Raw export content
        office_name: Office name for filename
        date_from: Start date
        date_to: End date
        output_dir: Output directory
        format: 'json' or 'csv'
        
    Returns:
        Path to saved file
    """
    # Create output directory
    output_path = Path(output_dir)
    output_path.mkdir(exist_ok=True)
    
    # Create filename
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    safe_name = office_name.replace(' ', '_').replace('/', '_')
    filename = f"{safe_name}_bookkeeping_{date_from}_to_{date_to}_{timestamp}.{format}"
    filepath = output_path / filename
    
    # Try to parse as JSON and save in requested format
    try:
        data = json.loads(content)
        
        if format == 'json':
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        
        elif format == 'csv':
            # Convert JSON to CSV
            if isinstance(data, list) and len(data) > 0:
                fieldnames = list(data[0].keys())
                with open(filepath, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.DictWriter(f, fieldnames=fieldnames)
                    writer.writeheader()
                    writer.writerows(data)
            else:
                logger.warning("Cannot convert to CSV: data is not a list")
                # Save as JSON instead
                filepath = filepath.with_suffix('.json')
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
        
        logger.info(f"💾 Saved: {filepath}")
        return str(filepath)
        
    except json.JSONDecodeError:
        # Not JSON, save as binary
        with open(filepath, 'wb') as f:
            f.write(content)
        logger.info(f"💾 Saved (binary): {filepath}")
        return str(filepath)


def export_and_save(
    token: str,
    office_id: str,
    office_name: str,
    date_from: str,
    date_to: str,
    env: str = "live",
    save_formats: List[str] = ['json', 'csv']
) -> Dict[str, str]:
    """
    Fetch bookkeeping data and save to files
    
    Args:
        token: Tebi API token
        office_id: Office ID
        office_name: Office name (for filename)
        date_from: Start date (YYYY-MM-DD)
        date_to: End date (YYYY-MM-DD)
        env: 'live' or 'test'
        save_formats: List of formats to save ('json', 'csv')
        
    Returns:
        Dict with format -> filepath mapping
    """
    client = make_client(token, env)
    
    try:
        # Fetch data
        content = fetch_bookkeeping_export(client, date_from, date_to, office_id)
        
        # Save in requested formats
        saved_files = {}
        for fmt in save_formats:
            filepath = save_export_to_file(
                content, office_name, date_from, date_to, 
                format=fmt
            )
            saved_files[fmt] = filepath
        
        return saved_files
        
    finally:
        client.close()


def export_last_n_days(
    token: str,
    office_id: str,
    office_name: str,
    days: int = 7,
    env: str = "live",
    save_formats: List[str] = ['json', 'csv']
) -> Dict[str, str]:
    """
    Export data for last N days
    
    Args:
        token: Tebi API token
        office_id: Office ID
        office_name: Office name
        days: Number of days to export
        env: 'live' or 'test'
        save_formats: Formats to save
        
    Returns:
        Dict with format -> filepath mapping
    """
    end_date = datetime.now().date()
    start_date = end_date - timedelta(days=days)
    
    return export_and_save(
        token=token,
        office_id=office_id,
        office_name=office_name,
        date_from=start_date.strftime('%Y-%m-%d'),
        date_to=end_date.strftime('%Y-%m-%d'),
        env=env,
        save_formats=save_formats
    )


def git_commit_and_push(files: List[str], commit_message: str) -> bool:
    """
    Commit files to Git and push to GitHub
    
    Args:
        files: List of file paths to commit
        commit_message: Commit message
        
    Returns:
        True if successful
    """
    import subprocess
    
    try:
        # Add files
        for file in files:
            subprocess.run(['git', 'add', file], check=True)
        
        # Commit
        subprocess.run(['git', 'commit', '-m', commit_message], check=True)
        
        # Push
        subprocess.run(['git', 'push'], check=True)
        
        logger.info(f"✅ Git: {commit_message}")
        return True
        
    except subprocess.CalledProcessError as e:
        logger.error(f"❌ Git error: {e}")
        return False
    except FileNotFoundError:
        logger.warning("Git not found - skipping commit")
        return False


# ==================== MAIN EXECUTION ====================

def main():
    """
    Main execution for automated exports
    Can be run from command line or GitHub Actions
    """
    # Get configuration from environment variables
    token = os.getenv('TEBI_API_TOKEN')
    office_id = os.getenv('TEBI_OFFICE_ID')
    office_name = os.getenv('TEBI_OFFICE_NAME', 'Unknown_Office')
    days = int(os.getenv('EXPORT_DAYS', '7'))
    env = os.getenv('TEBI_ENV', 'live')
    
    if not token or not office_id:
        logger.error("❌ Missing required environment variables:")
        logger.error("   TEBI_API_TOKEN - Your Tebi API token")
        logger.error("   TEBI_OFFICE_ID - Office/venue ID")
        logger.error("   TEBI_OFFICE_NAME - Office name (optional)")
        return
    
    logger.info(f"🚀 Starting Tebi export for {office_name}")
    logger.info(f"   Last {days} days from {env} environment")
    
    try:
        # Export data
        files = export_last_n_days(
            token=token,
            office_id=office_id,
            office_name=office_name,
            days=days,
            env=env,
            save_formats=['json', 'csv']
        )
        
        logger.info(f"✅ Export complete!")
        for fmt, filepath in files.items():
            logger.info(f"   {fmt.upper()}: {filepath}")
        
        # Commit to Git if in a repository
        if os.path.exists('.git'):
            commit_msg = f"🤖 Tebi export: {office_name} - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            git_commit_and_push(list(files.values()), commit_msg)
        
    except Exception as e:
        logger.error(f"❌ Export failed: {e}")
        raise


if __name__ == "__main__":
    main()
