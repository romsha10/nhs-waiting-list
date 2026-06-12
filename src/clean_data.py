# src/clean_data.py
# ─────────────────────────────────────────────────────────────────────────────
# PURPOSE: Clean and structure the raw NHS Scotland waiting times data
#          for use in forecasting (Phase 3) and risk scoring (Phase 4)
#
# KEY DECISIONS:
# - Drop all "QF" (Quality Flag) columns — they are metadata, not metrics
# - Parse MonthEnd / QuarterEnding into proper datetime objects
# - Create a single column "Over12WeekWait" = sum of all wait bands >= 12 weeks
#   This is the breach metric — the 12-week Treatment Time Guarantee (TTG)
# - Create "PctOver12Weeks" = Over12WeekWait / TotalWaiting * 100
#   This is what we forecast and apply traffic light logic to
# - Map HBT codes to human-readable Health Board names
# - Output one clean master CSV to data/processed/
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
import os

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"

# ── Health Board code → name mapping ─────────────────────────────────────────
# Source: NHS Scotland official codes
HB_NAMES = {
    "S92000003": "NHS Scotland (All)",
    "S08000015": "NHS Ayrshire & Arran",
    "S08000016": "NHS Borders",
    "S08000017": "NHS Dumfries & Galloway",
    "S08000019": "NHS Forth Valley",
    "S08000020": "NHS Grampian",
    "S08000022": "NHS Highland",
    "S08000024": "NHS Lothian",
    "S08000025": "NHS Orkney",
    "S08000026": "NHS Shetland",
    "S08000028": "NHS Western Isles",
    "S08000029": "NHS Fife",
    "S08000030": "NHS Tayside",
    "S08000031": "NHS Greater Glasgow & Clyde",
    "S08000032": "NHS Lanarkshire",
    "S27000001": "NHS Golden Jubilee",
    # Hospital-level codes that appear in the data
    "RA2702":    "NHS Ayrshire & Arran",
    "RA228H":    "NHS Ayrshire & Arran",
}

# ── Specialty code → name mapping ─────────────────────────────────────────────
# Common NHS Scotland specialty codes
SPECIALTY_NAMES = {
    "Z9":  "All Specialties",
    "A1":  "General Surgery",
    "A11": "Laparoscopic Surgery",
    "B1":  "Urology",
    "C1":  "Cardiothoracic Surgery",
    "C11": "Cardiac Surgery",
    "C12": "Thoracic Surgery",
    "C3":  "Plastic Surgery",
    "C31": "Cleft Lip & Palate",
    "C4":  "Ear Nose & Throat",
    "C41": "Audiological Medicine",
    "C5":  "Gynaecology",
    "C51": "Obstetrics",
    "C6":  "Ophthalmology",
    "C7":  "Orthopaedics",
    "C8":  "Neurosurgery",
    "C9":  "Oral Surgery",
    "D1":  "Neurology",
    "D3":  "Gastroenterology",
    "D4":  "Endocrinology",
    "D5":  "Haematology",
    "D6":  "Immunology",
    "D8":  "Respiratory Medicine",
    "E1":  "Cardiology",
    "E11": "Cardiac Rehabilitation",
    "E12": "Interventional Cardiology",
    "F1":  "Dermatology",
    "F3":  "Rheumatology",
    "G1":  "Geriatric Medicine",
    "G2":  "Rehabilitation Medicine",
    "H1":  "Psychiatry",
    "H2":  "Child Psychiatry",
    "J4":  "Radiology",
    "J8":  "Clinical Oncology",
    "R1":  "Paediatrics",
    "T1":  "Orthodontics",
    "T2":  "Restorative Dentistry",
}

# ── Helper: drop all quality flag columns ─────────────────────────────────────

def drop_qf_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    QF = Quality Flag. Every data column has a paired QF column
    e.g. 'NumberWaiting' and 'NumberWaitingQF'.
    QF columns contain NHS internal data quality codes — not useful for us.
    We identify them by the 'QF' suffix and drop them all.
    """
    qf_cols = [c for c in df.columns if c.endswith("QF")]
    return df.drop(columns=qf_cols)

# ── Helper: parse NHS date formats ───────────────────────────────────────────

def parse_nhs_date(series: pd.Series) -> pd.Series:
    """
    NHS Scotland uses YYYYMMDD integers for dates e.g. 20190630.
    Convert to proper pandas datetime for time series use.
    """
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")

# ── Helper: map codes to names ────────────────────────────────────────────────

def map_codes(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add human-readable columns alongside the raw code columns.
    We keep the original codes too — useful for joining later.
    Unknown codes get labelled 'Other/Unknown (CODE)' so nothing is lost.
    """
    df["HealthBoardName"] = df["HBT"].map(HB_NAMES).fillna(
        df["HBT"].apply(lambda x: f"Other/Unknown ({x})")
    )
    if "Specialty" in df.columns:
        df["SpecialtyName"] = df["Specialty"].map(SPECIALTY_NAMES).fillna(
            df["Specialty"].apply(lambda x: f"Specialty ({x})")
        )
    return df

# ── Clean: ongoing_waits_long_trend ──────────────────────────────────────────

def clean_ongoing_waits() -> pd.DataFrame:
    """
    This is the PRIMARY dataset for forecasting.
    It contains monthly counts of patients CURRENTLY waiting,
    broken into time bands (0-4 weeks, 4-8 weeks ... over 156 weeks).

    We calculate:
    - TotalWaiting: sum of ALL wait band columns
    - Over12WeekWait: sum of all bands >= 12 weeks (the breach threshold)
    - PctOver12Weeks: Over12WeekWait / TotalWaiting * 100

    The 12-week TTG (Treatment Time Guarantee) is the NHS Scotland legal target.
    Any patient waiting over 12 weeks = a breach.
    """
    print("  Cleaning: ongoing_waits_long_trend")
    df = pd.read_csv(
        f"{RAW_DIR}/ongoing_waits_long_trend.csv",
        low_memory=False
    )

    df = drop_qf_columns(df)
    df["Date"] = parse_nhs_date(df["MonthEnd"])
    df = map_codes(df)

    # Identify all wait band columns — they all follow the pattern *WeekWait
    wait_band_cols = [c for c in df.columns if "WeekWait" in c or "Week" in c
                      and c not in ["LessThan4WeekWait"]]

    # More precise: grab exactly the columns we want
    all_band_cols = [c for c in df.columns if c.endswith("WeekWait")]

    # Bands that are >= 12 weeks = breach territory
    over_12_cols = [c for c in all_band_cols if not c.startswith("LessThan4")
                    and not c.startswith("4To8")
                    and not c.startswith("8To12")]

    # Total waiting = sum of all bands
    df["TotalWaiting"] = df[all_band_cols].sum(axis=1)

    # Over 12 weeks waiting
    df["Over12WeekWait"] = df[over_12_cols].sum(axis=1)

    # Percentage breaching
    df["PctOver12Weeks"] = (
        df["Over12WeekWait"] / df["TotalWaiting"].replace(0, pd.NA) * 100
    ).round(2)

    # Select final clean columns
    keep_cols = [
        "Date", "HBT", "HealthBoardName",
        "PatientType", "Specialty", "SpecialtyName",
        "TotalWaiting", "Over12WeekWait", "PctOver12Weeks",
    ] + all_band_cols

    df = df[keep_cols].copy()

    # Drop rows where Date couldn't be parsed or TotalWaiting is zero
    df = df.dropna(subset=["Date"])
    df = df[df["TotalWaiting"] > 0]

    df = df.sort_values(["HBT", "Specialty", "PatientType", "Date"])
    df = df.reset_index(drop=True)

    print(f"  Shape: {df.shape}")
    print(f"  Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")
    print(f"  Health Boards: {df['HealthBoardName'].nunique()}")
    print(f"  Specialties: {df['Specialty'].nunique()}")
    print(f"  Sample PctOver12Weeks range: {df['PctOver12Weeks'].min():.1f}% → {df['PctOver12Weeks'].max():.1f}%")

    return df

# ── Clean: ongoing_waits_monthly ─────────────────────────────────────────────

def clean_monthly_waits() -> pd.DataFrame:
    """
    Most recent 25 months of performance data.
    Contains NumberWaiting and NumberSeenWithin12Weeks columns.
    Used as a cross-check against the long trend data.
    """
    print("\n  Cleaning: ongoing_waits_monthly")
    df = pd.read_csv(
        f"{RAW_DIR}/ongoing_waits_monthly.csv",
        low_memory=False
    )

    df = drop_qf_columns(df)
    df["Date"] = parse_nhs_date(df["MonthEnd"])
    df = map_codes(df)

    df = df.dropna(subset=["Date"])
    df = df.sort_values(["HBT", "Specialty", "PatientType", "Date"])
    df = df.reset_index(drop=True)

    print(f"  Shape: {df.shape}")
    print(f"  Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")
    print(f"  Columns: {list(df.columns)}")

    return df

# ── Clean: additions_and_removals ────────────────────────────────────────────

def clean_additions_removals() -> pd.DataFrame:
    """
    Quarterly data on how many patients are ADDED to and REMOVED from lists.
    Additions - Removals = net pressure on the system.
    A positive and growing gap = waiting list growing = future breach risk.
    We'll use this as a supplementary feature in the risk engine.
    """
    print("\n  Cleaning: additions_and_removals")
    df = pd.read_csv(
        f"{RAW_DIR}/additions_and_removals.csv",
        low_memory=False
    )

    df = drop_qf_columns(df)
    df["Date"] = parse_nhs_date(df["QuarterEnding"])
    df = map_codes(df)

    # Net pressure = more additions than removals = list is growing
    df["NetPressure"] = df["Additions"] - df["Removals"]

    df = df.dropna(subset=["Date", "Additions", "Removals"])
    df = df.sort_values(["HBT", "Specialty", "PatientType", "Date"])
    df = df.reset_index(drop=True)

    print(f"  Shape: {df.shape}")
    print(f"  Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")

    return df

# ── Main ──────────────────────────────────────────────────────────────────────

def clean_all():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("\n── Phase 2: Cleaning NHS Waiting Times Data ────────────────────────\n")

    # Clean each dataset
    df_ongoing   = clean_ongoing_waits()
    df_monthly   = clean_monthly_waits()
    df_additions = clean_additions_removals()

    # Save to processed/
    ongoing_path   = f"{PROCESSED_DIR}/ongoing_waits_clean.csv"
    monthly_path   = f"{PROCESSED_DIR}/monthly_waits_clean.csv"
    additions_path = f"{PROCESSED_DIR}/additions_removals_clean.csv"

    df_ongoing.to_csv(ongoing_path, index=False)
    df_monthly.to_csv(monthly_path, index=False)
    df_additions.to_csv(additions_path, index=False)

    print("\n── Saved Files ─────────────────────────────────────────────────────")
    print(f"  ✓ {ongoing_path}   ({len(df_ongoing):,} rows)")
    print(f"  ✓ {monthly_path}  ({len(df_monthly):,} rows)")
    print(f"  ✓ {additions_path} ({len(df_additions):,} rows)")

    # Quick sanity check — show top 5 Health Boards by current breach %
    print("\n── Top 10 Health Board + Specialty combinations by breach % ────────")
    latest_date = df_ongoing["Date"].max()
    latest = df_ongoing[
        (df_ongoing["Date"] == latest_date) &
        (df_ongoing["HBT"] != "S92000003") &   # exclude national aggregate
        (df_ongoing["Specialty"] != "Z9")        # exclude all-specialty aggregate
    ].copy()

    top10 = (
        latest.groupby(["HealthBoardName", "SpecialtyName", "PatientType"])
        ["PctOver12Weeks"]
        .mean()
        .reset_index()
        .sort_values("PctOver12Weeks", ascending=False)
        .head(10)
    )

    for _, row in top10.iterrows():
        bar = "█" * int(row["PctOver12Weeks"] / 5)
        print(f"  {row['PctOver12Weeks']:5.1f}%  {bar}")
        print(f"         {row['HealthBoardName']} — {row['SpecialtyName']} ({row['PatientType']})")

    print(f"\n  Latest data date: {latest_date.date()}")
    print("\n── Phase 2 Complete ────────────────────────────────────────────────")
    print("Next: run src/forecast.py (Phase 3)\n")

    return df_ongoing, df_monthly, df_additions


if __name__ == "__main__":
    clean_all()
