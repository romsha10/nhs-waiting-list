# src/clean_data.py
# ─────────────────────────────────────────────────────────────────────────────
# PURPOSE: Clean and structure raw NHS Scotland waiting times data
#
# KEY FIX: ongoing_waits_long_trend uses 'MonthEnding' (not 'MonthEnd')
#          and already has 'NumberWaitingOver12Weeks' pre-calculated.
#          We use that directly — no need to sum wait bands manually.
#
# FINAL COLUMNS WE CARE ABOUT:
#   Date, HBT, HealthBoardName, PatientType, Specialty, SpecialtyName,
#   NumberWaiting, NumberWaitingOver12Weeks, PctOver12Weeks
# ─────────────────────────────────────────────────────────────────────────────

import pandas as pd
import os

RAW_DIR = "data/raw"
PROCESSED_DIR = "data/processed"

# ── Health Board code → name mapping ─────────────────────────────────────────
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
}

# ── Specialty code → name mapping ─────────────────────────────────────────────
SPECIALTY_NAMES = {
    "Z9":  "All Specialties",
    "A1":  "General Surgery",
    "B1":  "Urology",
    "C1":  "Cardiothoracic Surgery",
    "C11": "Cardiac Surgery",
    "C12": "Thoracic Surgery",
    "C3":  "Plastic Surgery",
    "C4":  "Ear Nose & Throat",
    "C41": "Audiological Medicine",
    "C5":  "Gynaecology",
    "C6":  "Ophthalmology",
    "C7":  "Orthopaedics",
    "C8":  "Neurosurgery",
    "C9":  "Oral Surgery",
    "D1":  "Neurology",
    "D3":  "Gastroenterology",
    "D4":  "Endocrinology",
    "D5":  "Haematology",
    "D8":  "Respiratory Medicine",
    "E1":  "Cardiology",
    "F1":  "Dermatology",
    "F3":  "Rheumatology",
    "G1":  "Geriatric Medicine",
    "G2":  "Rehabilitation Medicine",
    "J8":  "Clinical Oncology",
    "R1":  "Paediatrics",
    "T1":  "Orthodontics",
    "T2":  "Restorative Dentistry",
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def drop_qf_columns(df):
    qf_cols = [c for c in df.columns if c.endswith("QF")]
    return df.drop(columns=qf_cols)

def parse_nhs_date(series):
    return pd.to_datetime(series.astype(str), format="%Y%m%d", errors="coerce")

def map_codes(df):
    df["HealthBoardName"] = df["HBT"].map(HB_NAMES).fillna(
        df["HBT"].apply(lambda x: f"Unknown ({x})")
    )
    if "Specialty" in df.columns:
        df["SpecialtyName"] = df["Specialty"].map(SPECIALTY_NAMES).fillna(
            df["Specialty"].apply(lambda x: f"Specialty ({x})")
        )
    return df

# ── Clean: ongoing_waits_long_trend ──────────────────────────────────────────

def clean_ongoing_waits():
    """
    PRIMARY dataset for forecasting.
    Date column is 'MonthEnding' (YYYYMMDD integer).
    NHS already provides NumberWaitingOver12Weeks directly.
    We calculate PctOver12Weeks = Over12 / Total * 100.
    This percentage is what Prophet will forecast in Phase 3.
    """
    print("  Cleaning: ongoing_waits_long_trend")
    df = pd.read_csv(f"{RAW_DIR}/ongoing_waits_long_trend.csv", low_memory=False)

    df = drop_qf_columns(df)

    # FIX: correct column name is MonthEnding not MonthEnd
    df["Date"] = parse_nhs_date(df["MonthEnding"])
    df = map_codes(df)

    # Core breach metric
    df["PctOver12Weeks"] = (
        df["NumberWaitingOver12Weeks"] /
        df["NumberWaiting"].replace(0, pd.NA) * 100
    ).round(2)

    keep = [
        "Date", "HBT", "HealthBoardName",
        "PatientType", "Specialty", "SpecialtyName",
        "NumberWaiting", "NumberWaitingOver12Weeks",
        "PctOver12Weeks", "Median", "90thPercentile"
    ]
    df = df[keep].dropna(subset=["Date"])
    df = df[df["NumberWaiting"] > 0]
    df = df.sort_values(["HBT", "Specialty", "PatientType", "Date"]).reset_index(drop=True)

    print(f"  Shape:         {df.shape}")
    print(f"  Date range:    {df['Date'].min().date()} → {df['Date'].max().date()}")
    print(f"  Health Boards: {df['HealthBoardName'].nunique()}")
    print(f"  Specialties:   {df['Specialty'].nunique()}")

    return df

# ── Clean: ongoing_waits_monthly ─────────────────────────────────────────────

def clean_monthly_waits():
    """
    Most recent 25 months. Cross-check against long trend.
    Date column here is 'MonthEnd'.
    """
    print("\n  Cleaning: ongoing_waits_monthly")
    df = pd.read_csv(f"{RAW_DIR}/ongoing_waits_monthly.csv", low_memory=False)

    df = drop_qf_columns(df)

    # Check which date column exists
    if "MonthEnd" in df.columns:
        df["Date"] = parse_nhs_date(df["MonthEnd"])
    elif "MonthEnding" in df.columns:
        df["Date"] = parse_nhs_date(df["MonthEnding"])

    df = map_codes(df)
    df = df.dropna(subset=["Date"])
    df = df.sort_values(["HBT", "Date"]).reset_index(drop=True)

    print(f"  Shape:      {df.shape}")
    print(f"  Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")
    print(f"  Columns:    {list(df.columns)}")

    return df

# ── Clean: additions_and_removals ────────────────────────────────────────────

def clean_additions_removals():
    """
    Quarterly additions vs removals. Net pressure = Additions - Removals.
    Growing net pressure = waiting list expanding = future breach signal.
    """
    print("\n  Cleaning: additions_and_removals")
    df = pd.read_csv(f"{RAW_DIR}/additions_and_removals.csv", low_memory=False)

    df = drop_qf_columns(df)
    df["Date"] = parse_nhs_date(df["QuarterEnding"])
    df = map_codes(df)

    df["NetPressure"] = df["Additions"] - df["Removals"]

    df = df.dropna(subset=["Date", "Additions", "Removals"])
    df = df.sort_values(["HBT", "Specialty", "PatientType", "Date"]).reset_index(drop=True)

    print(f"  Shape:      {df.shape}")
    print(f"  Date range: {df['Date'].min().date()} → {df['Date'].max().date()}")

    return df

# ── Main ──────────────────────────────────────────────────────────────────────

def clean_all():
    os.makedirs(PROCESSED_DIR, exist_ok=True)

    print("\n── Phase 2: Cleaning NHS Waiting Times Data ────────────────────────\n")

    df_ongoing   = clean_ongoing_waits()
    df_monthly   = clean_monthly_waits()
    df_additions = clean_additions_removals()

    # Save
    df_ongoing.to_csv(f"{PROCESSED_DIR}/ongoing_waits_clean.csv", index=False)
    df_monthly.to_csv(f"{PROCESSED_DIR}/monthly_waits_clean.csv", index=False)
    df_additions.to_csv(f"{PROCESSED_DIR}/additions_removals_clean.csv", index=False)

    print("\n── Saved ───────────────────────────────────────────────────────────")
    print(f"  ✓ processed/ongoing_waits_clean.csv     ({len(df_ongoing):,} rows)")
    print(f"  ✓ processed/monthly_waits_clean.csv     ({len(df_monthly):,} rows)")
    print(f"  ✓ processed/additions_removals_clean.csv ({len(df_additions):,} rows)")

    # ── Sanity check: top 10 breach combinations right now ───────────────────
    print("\n── Current Worst Breach % (latest month, by Health Board & Specialty)")
    latest_date = df_ongoing["Date"].max()
    latest = df_ongoing[
        (df_ongoing["Date"] == latest_date) &
        (df_ongoing["HBT"] != "S92000003") &
        (df_ongoing["Specialty"] != "Z9")
    ]

    top10 = (
        latest.groupby(["HealthBoardName", "SpecialtyName", "PatientType"])["PctOver12Weeks"]
        .mean().reset_index()
        .sort_values("PctOver12Weeks", ascending=False)
        .head(10)
    )

    print(f"  (Data as of {latest_date.date()})\n")
    for _, row in top10.iterrows():
        bar = "█" * int(row["PctOver12Weeks"] / 5)
        flag = "🔴" if row["PctOver12Weeks"] > 50 else ("🟡" if row["PctOver12Weeks"] > 20 else "🟢")
        print(f"  {flag} {row['PctOver12Weeks']:5.1f}%  {bar}")
        print(f"          {row['HealthBoardName']} | {row['SpecialtyName']} | {row['PatientType']}\n")

    print("── Phase 2 Complete ─────────────────────────────────────────────────")
    print("Next: run src/forecast.py (Phase 3)\n")

    return df_ongoing, df_monthly, df_additions


if __name__ == "__main__":
    clean_all()
