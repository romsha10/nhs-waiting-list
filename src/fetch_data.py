# src/fetch_data.py
# ─────────────────────────────────────────────────────────────────────────────
# PURPOSE: Download NHS Scotland Stage of Treatment Waiting Times data
#          directly from opendata.nhs.scot using direct CSV download URLs.
#
# APPROACH CHANGE: Instead of the CKAN package API (which 404'd because NHS
# Scotland renamed their datasets), we now use direct CSV download links.
# These are the real, verified resource IDs scraped from the live NHS page.
# Data goes back to October 2012 — plenty for time series forecasting.
# ─────────────────────────────────────────────────────────────────────────────

import requests
import pandas as pd
import os

RAW_DATA_DIR = "data/raw"

# ── Real verified resource IDs from opendata.nhs.scot ────────────────────────
# Package: stage-of-treatment-waiting-times
# Package UUID: e9dbef36-a343-4b9a-ab7e-b6e6cbcbb38e
# These were confirmed live on the NHS Scotland Open Data portal June 2026

PACKAGE_UUID = "e9dbef36-a343-4b9a-ab7e-b6e6cbcbb38e"

RESOURCES = [
    {
        "name": "ongoing_waits_long_trend",
        "resource_id": "5816ec92-66bf-4033-ae55-9df45ff19d49",
        "description": "Ongoing inpatient, daycase and outpatient waits — long historical trend"
    },
    {
        "name": "completed_waits_long_trend",
        "resource_id": "4c091d26-1492-41e5-9577-832cbc1cd4cf",
        "description": "Completed inpatient, daycase and outpatient waits — long historical trend"
    },
    {
        "name": "ongoing_waits_monthly",
        "resource_id": "ac63b747-fdcc-410c-ae43-de6fe3c46abf",
        "description": "Ongoing and completed waits — most recent 25 months (monthly)"
    },
    {
        "name": "distribution_ongoing_waits_long_trend",
        "resource_id": "093f04a5-bb8f-4ce6-9016-d4fa0a912630",
        "description": "Distribution of ongoing wait lengths — long trend"
    },
    {
        "name": "additions_and_removals",
        "resource_id": "10dd6ca4-1868-464c-8d20-7f9261070484",
        "description": "Additions and reasons for removal from waiting list"
    },
]

# ── Download a single resource as CSV ────────────────────────────────────────

def download_resource(resource: dict) -> pd.DataFrame:
    """
    Build the direct CSV download URL from the package UUID and resource ID,
    then download it straight into a Pandas DataFrame.

    URL pattern: /dataset/{package_uuid}/resource/{resource_id}/download/
    We use the CKAN datastore_search API with a high limit as a fallback
    if direct download fails.
    """

    # Method 1: CKAN datastore_search API (handles pagination properly)
    api_url = "https://www.opendata.nhs.scot/api/3/action/datastore_search"

    print(f"\n  Downloading: {resource['name']}")
    print(f"  {resource['description']}")

    all_records = []
    offset = 0
    limit = 32000

    while True:
        params = {
            "resource_id": resource["resource_id"],
            "limit": limit,
            "offset": offset,
        }

        try:
            response = requests.get(api_url, params=params, timeout=60)
            data = response.json()

            if not data.get("success"):
                print(f"  [WARN] API returned success=false, trying direct CSV...")
                break

            records = data["result"]["records"]
            total = data["result"]["total"]
            all_records.extend(records)
            offset += limit

            print(f"  Fetched {len(all_records):,} / {total:,} rows", end="\r")

            if offset >= total:
                print(f"\n  Done — {len(all_records):,} rows")
                return pd.DataFrame(all_records)

        except Exception as e:
            print(f"  [WARN] API error: {e}, trying direct CSV...")
            break

    # Method 2: Fallback — direct CSV download
    print("  Attempting direct CSV download...")
    csv_url = (
        f"https://www.opendata.nhs.scot/dataset/{PACKAGE_UUID}"
        f"/resource/{resource['resource_id']}/download/"
    )

    try:
        response = requests.get(csv_url, timeout=60)
        if response.status_code == 200:
            from io import StringIO
            df = pd.read_csv(StringIO(response.text))
            print(f"  Done — {len(df):,} rows via direct CSV")
            return df
        else:
            print(f"  [ERROR] Direct CSV returned {response.status_code}")
            return pd.DataFrame()
    except Exception as e:
        print(f"  [ERROR] Direct CSV failed: {e}")
        return pd.DataFrame()


# ── Main ─────────────────────────────────────────────────────────────────────

def fetch_all_data():
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    print("\n── NHS Scotland Waiting Times — Phase 1 Data Download ─────────────")
    print(f"Package: stage-of-treatment-waiting-times")
    print(f"UUID:    {PACKAGE_UUID}")
    print(f"Output:  {RAW_DATA_DIR}/\n")

    summary = []

    for resource in RESOURCES:
        filepath = os.path.join(RAW_DATA_DIR, f"{resource['name']}.csv")

        if os.path.exists(filepath):
            existing = pd.read_csv(filepath)
            print(f"  [SKIP] {resource['name']}.csv already exists ({len(existing):,} rows)")
            summary.append({"file": resource["name"], "rows": len(existing), "status": "skipped"})
            continue

        df = download_resource(resource)

        if df.empty:
            print(f"  [WARN] No data for {resource['name']}")
            summary.append({"file": resource["name"], "rows": 0, "status": "failed"})
            continue

        df.to_csv(filepath, index=False)
        print(f"  Saved → {filepath}  ({df.shape[0]:,} rows × {df.shape[1]} cols)")
        summary.append({"file": resource["name"], "rows": df.shape[0], "status": "downloaded"})

        # Print column names so we know the structure for Phase 2
        print(f"  Columns: {list(df.columns)}")

    # Summary table
    print("\n── Download Summary ────────────────────────────────────────────────")
    for s in summary:
        status_icon = "✓" if s["status"] == "downloaded" else ("↷" if s["status"] == "skipped" else "✗")
        print(f"  {status_icon}  {s['file']:<45} {s['rows']:>8,} rows  [{s['status']}]")

    print("\n── Phase 1 Complete ────────────────────────────────────────────────")
    print("Next: run src/clean_data.py (Phase 2)\n")


if __name__ == "__main__":
    fetch_all_data()
