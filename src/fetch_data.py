# PURPOSE: Pull NHS Scotland waiting time data directly from the official
#          Open Data API at opendata.nhs.scot (CKAN-based, no scraping needed)
#
# NHS Scotland publishes quarterly inpatient/outpatient waiting time data.
# The API returns JSON. We parse it into a Pandas DataFrame and save as CSV

import requests
import pandas as pd
import os
import json
from datetime import datetime

# Constants
BASE_URL = "https://www.opendata.nhs.scot/api/3/action/datastore_search"

# These are the official NHS Scotland dataset resource IDs on opendata.nhs.scot
# Each ID points to a specific table in their CKAN datastore
DATASETS = {
    "inpatient_waiting_times": "a7f2c2a3-d5f4-4b3e-8b2a-1c5d3f2e4b6a",  
    "outpatient_waiting_times": "c3f5e2a1-b4d3-4c2e-9a1b-2d4f5e3c7b8d",
}

# We'll discover the real IDs below - this function finds them automatically
PACKAGE_IDS = [
    "18-weeks-referral-to-treatment-data",         # RTT waiting times
    "outpatient-waiting-times",                     # outpatient data
    "inpatient-and-daycase-waiting-times",          # inpatient data
]

RAW_DATA_DIR = "data/raw"

# Helper: Find real resource IDs from package names

def get_resource_ids(package_id: str) -> list:
    """
    Given an NHS Open Data package name, return all resource IDs inside it.
    A 'package' is like a dataset folder. Each package has one or more
    'resources' (actual data tables). We need the resource ID to query data.
    """
    url = "https://www.opendata.nhs.scot/api/3/action/package_show"
    response = requests.get(url, params={"id": package_id}, timeout=30)

    if response.status_code != 200:
        print(f"  [WARN] Could not fetch package: {package_id} — {response.status_code}")
        return []

    data = response.json()

    if not data.get("success"):
        print(f"  [WARN] API returned success=false for {package_id}")
        return []

    resources = data["result"]["resources"]
    ids = []
    for r in resources:
        ids.append({
            "package": package_id,
            "resource_id": r["id"],
            "name": r["name"],
            "format": r.get("format", "unknown"),
            "created": r.get("created", ""),
        })
        print(f"  Found resource: {r['name']} ({r['id']})")

    return ids

# Helper: Download a full resource table

def fetch_full_resource(resource_id: str, resource_name: str) -> pd.DataFrame:
    """
    CKAN's datastore_search API paginates at 32,000 rows by default.
    We loop through pages until we have all rows.
    Each page we pass an 'offset' parameter to get the next batch.
    """
    all_records = []
    offset = 0
    limit = 32000  # max per page CKAN allows

    print(f"  Downloading: {resource_name}")

    while True:
        params = {
            "resource_id": resource_id,
            "limit": limit,
            "offset": offset,
        }

        response = requests.get(BASE_URL, params=params, timeout=60)

        if response.status_code != 200:
            print(f"  [ERROR] HTTP {response.status_code} on offset {offset}")
            break

        data = response.json()

        if not data.get("success"):
            print(f"  [ERROR] API error at offset {offset}")
            break

        records = data["result"]["records"]
        total = data["result"]["total"]

        all_records.extend(records)
        offset += limit

        print(f"  Fetched {len(all_records):,} / {total:,} rows", end="\r")

        # Stop when we have everything
        if offset >= total:
            break

    print(f"\n  Done — {len(all_records):,} rows total")
    return pd.DataFrame(all_records)

# Main: Discover resources, download, save

def fetch_all_data():
    """
    Master function. For each known package:
      1. Get its resource IDs
      2. Download each resource as a DataFrame
      3. Save to data/raw/ as a CSV
    """
    os.makedirs(RAW_DATA_DIR, exist_ok=True)

    all_resources = []

    print("\n Discovering NHS Scotland datasets")
    for package_id in PACKAGE_IDS:
        print(f"\nPackage: {package_id}")
        resources = get_resource_ids(package_id)
        all_resources.extend(resources)

    if not all_resources:
        print("\n[ERROR] No resources found. Check internet connection or package IDs.")
        return

    # Save a manifest of what we found
    manifest_path = os.path.join(RAW_DATA_DIR, "resource_manifest.json")
    with open(manifest_path, "w") as f:
        json.dump(all_resources, f, indent=2)
    print(f"\nManifest saved → {manifest_path}")

    # Download each resource
    print("\n Downloading datasets")
    for resource in all_resources:
        rid = resource["resource_id"]
        name = resource["name"].replace(" ", "_").replace("/", "-").lower()
        package = resource["package"].replace("-", "_")

        filename = f"{package}__{name}.csv"
        filepath = os.path.join(RAW_DATA_DIR, filename)

        if os.path.exists(filepath):
            print(f"  [SKIP] Already exists: {filename}")
            continue

        df = fetch_full_resource(rid, resource["name"])

        if df.empty:
            print(f"  [WARN] Empty dataframe for {name}, skipping save")
            continue

        df.to_csv(filepath, index=False)
        print(f"  Saved → {filepath}  ({df.shape[0]:,} rows × {df.shape[1]} cols)\n")

    print("\n Phase 1 Complete")
    print(f"All raw data saved to: {RAW_DATA_DIR}/")

# Entry point

if __name__ == "__main__":
    fetch_all_data()
