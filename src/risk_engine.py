# src/risk_engine.py
# -----------------------------------------------------------------------------
# PURPOSE: Apply traffic light risk classification to every forecasted
#          department combination and produce a single risk scores CSV
#          that the Streamlit app and Power BI dashboard will consume.
#
# TRAFFIC LIGHT LOGIC:
#   We look at the PEAK forecasted PctOver12Weeks across the 6-month horizon.
#
#   GREEN  : peak forecast < 20%   -- comfortably within target
#   AMBER  : peak forecast 20-50%  -- at risk, needs monitoring
#   RED    : peak forecast > 50%   -- breach predicted, action required
#
#   These thresholds are based on NHS Scotland TTG reporting conventions.
#   Boards consistently above 50% are flagged in official PHS publications.
#
# SECONDARY SIGNALS (added to give managers richer context):
#   - Trend direction: is breach % rising or falling over last 6 months?
#   - Pressure score: net additions vs removals from waiting list
#   - Confidence band width: how uncertain is the forecast?
#
# OUTPUT:
#   data/processed/risk_scores.csv -- one row per department, final risk label
# -----------------------------------------------------------------------------

import pandas as pd
import numpy as np
import os

PROCESSED_DIR = "data/processed"

# Traffic light thresholds
GREEN_MAX  = 20.0   # below this = GREEN
AMBER_MAX  = 50.0   # below this = AMBER, above = RED

# -----------------------------------------------------------------------------
# Load data
# -----------------------------------------------------------------------------

def load_inputs():
    forecasts = pd.read_csv(
        f"{PROCESSED_DIR}/forecasts.csv",
        parse_dates=["ForecastDate"]
    )
    ongoing = pd.read_csv(
        f"{PROCESSED_DIR}/ongoing_waits_clean.csv",
        parse_dates=["Date"]
    )
    additions = pd.read_csv(
        f"{PROCESSED_DIR}/additions_removals_clean.csv",
        parse_dates=["Date"]
    )
    return forecasts, ongoing, additions

# -----------------------------------------------------------------------------
# Signal 1: Traffic light from peak forecast
# -----------------------------------------------------------------------------

def apply_traffic_light(peak_pct: float) -> str:
    if peak_pct >= AMBER_MAX:
        return "RED"
    elif peak_pct >= GREEN_MAX:
        return "AMBER"
    else:
        return "GREEN"

# -----------------------------------------------------------------------------
# Signal 2: Trend direction over last 6 months of actual data
# -----------------------------------------------------------------------------

def compute_trend(ongoing: pd.DataFrame) -> pd.DataFrame:
    """
    For each department, fit a simple linear slope to the last 6 months
    of PctOver12Weeks. Positive slope = worsening. Negative = improving.

    We express slope as change in percentage points per month, rounded to 1dp.
    e.g. +2.3 means breach % is rising 2.3 points per month -- alarming.
         -1.1 means breach % is falling 1.1 points per month -- improving.
    """
    results = []
    cutoff = ongoing["Date"].max() - pd.DateOffset(months=6)
    recent = ongoing[ongoing["Date"] >= cutoff].copy()

    groups = recent.groupby(["HBT", "Specialty", "PatientType"])

    for (hbt, spec, pt), grp in groups:
        grp = grp.sort_values("Date").dropna(subset=["PctOver12Weeks"])
        if len(grp) < 3:
            slope = 0.0
        else:
            # Convert dates to numeric (months from start)
            x = (grp["Date"] - grp["Date"].min()).dt.days / 30.0
            y = grp["PctOver12Weeks"].values
            # np.polyfit returns [slope, intercept]
            slope = float(np.polyfit(x, y, 1)[0])

        if slope > 0.5:
            trend_label = "Worsening"
        elif slope < -0.5:
            trend_label = "Improving"
        else:
            trend_label = "Stable"

        results.append({
            "HBT": hbt,
            "Specialty": spec,
            "PatientType": pt,
            "TrendSlope": round(slope, 2),
            "TrendDirection": trend_label,
        })

    return pd.DataFrame(results)

# -----------------------------------------------------------------------------
# Signal 3: Current actual breach % (latest available data point)
# -----------------------------------------------------------------------------

def get_current_breach(ongoing: pd.DataFrame) -> pd.DataFrame:
    latest_date = ongoing["Date"].max()
    latest = ongoing[ongoing["Date"] == latest_date].copy()
    return latest[[
        "HBT", "HealthBoardName", "Specialty", "SpecialtyName",
        "PatientType", "NumberWaiting", "NumberWaitingOver12Weeks",
        "PctOver12Weeks", "Median", "90thPercentile"
    ]].rename(columns={
        "PctOver12Weeks": "CurrentPctOver12Weeks",
        "Median": "CurrentMedianWaitWeeks",
        "90thPercentile": "Current90thPctWaitWeeks",
    })

# -----------------------------------------------------------------------------
# Signal 4: Net pressure from additions/removals (latest quarter)
# -----------------------------------------------------------------------------

def get_pressure(additions: pd.DataFrame) -> pd.DataFrame:
    latest_q = additions["Date"].max()
    latest = additions[additions["Date"] == latest_q].copy()
    return latest[["HBT", "Specialty", "PatientType",
                   "Additions", "Removals", "NetPressure"]]

# -----------------------------------------------------------------------------
# Main: combine all signals into one risk score table
# -----------------------------------------------------------------------------

def build_risk_scores():
    print("\n-- Phase 4: Risk Engine ------------------------------------------------\n")

    print("  Loading forecasts and clean data...")
    forecasts, ongoing, additions = load_inputs()

    # -- Forecast summary per department: peak, mean, final forecast value ----
    print("  Computing forecast summary per department...")
    forecast_summary = (
        forecasts.groupby(["HBT", "HealthBoardName", "Specialty", "SpecialtyName", "PatientType"])
        .agg(
            PeakForecast        =("yhat", "max"),
            MeanForecast        =("yhat", "mean"),
            FinalForecast       =("yhat", "last"),
            ForecastUncertainty =("yhat_upper", lambda x: (
                forecasts.loc[x.index, "yhat_upper"] -
                forecasts.loc[x.index, "yhat_lower"]
            ).mean().round(2)),
            ForecastDateMax     =("ForecastDate", "max"),
        )
        .reset_index()
    )

    forecast_summary["PeakForecast"]  = forecast_summary["PeakForecast"].round(2)
    forecast_summary["MeanForecast"]  = forecast_summary["MeanForecast"].round(2)
    forecast_summary["FinalForecast"] = forecast_summary["FinalForecast"].round(2)

    # -- Apply traffic light --------------------------------------------------
    forecast_summary["RiskRating"] = forecast_summary["PeakForecast"].apply(apply_traffic_light)

    counts = forecast_summary["RiskRating"].value_counts()
    print(f"  GREEN  (safe)          : {counts.get('GREEN', 0):>4} departments")
    print(f"  AMBER  (at risk)       : {counts.get('AMBER', 0):>4} departments")
    print(f"  RED    (breach likely) : {counts.get('RED',   0):>4} departments")

    # -- Trend signal ---------------------------------------------------------
    print("\n  Computing trend direction (last 6 months)...")
    trends = compute_trend(ongoing)

    # -- Current breach state -------------------------------------------------
    current = get_current_breach(ongoing)

    # -- Pressure signal ------------------------------------------------------
    pressure = get_pressure(additions)

    # -- Merge everything together --------------------------------------------
    print("  Merging all signals...")

    risk = forecast_summary.merge(
        current,  on=["HBT", "HealthBoardName", "Specialty", "SpecialtyName", "PatientType"],
        how="left"
    )
    risk = risk.merge(
        trends,   on=["HBT", "Specialty", "PatientType"],
        how="left"
    )
    risk = risk.merge(
        pressure, on=["HBT", "Specialty", "PatientType"],
        how="left"
    )

    # -- Priority score (for sorting in dashboard) ----------------------------
    # Combines traffic light + trend to give a single urgency number
    # RED=3, AMBER=2, GREEN=1, then worsening trend adds 0.5
    risk["PriorityScore"] = risk["RiskRating"].map({"RED": 3, "AMBER": 2, "GREEN": 1})
    risk.loc[risk["TrendDirection"] == "Worsening", "PriorityScore"] += 0.5
    risk.loc[risk["TrendDirection"] == "Improving",  "PriorityScore"] -= 0.3
    risk["PriorityScore"] = risk["PriorityScore"].round(2)

    # -- Final column order ---------------------------------------------------
    col_order = [
        "HBT", "HealthBoardName", "Specialty", "SpecialtyName", "PatientType",
        "RiskRating", "PriorityScore",
        "CurrentPctOver12Weeks", "PeakForecast", "MeanForecast", "FinalForecast",
        "ForecastUncertainty", "ForecastDateMax",
        "TrendDirection", "TrendSlope",
        "CurrentMedianWaitWeeks", "Current90thPctWaitWeeks",
        "NumberWaiting", "NumberWaitingOver12Weeks",
        "Additions", "Removals", "NetPressure",
    ]
    # Only keep columns that exist (some merges may not have matched)
    col_order = [c for c in col_order if c in risk.columns]
    risk = risk[col_order].sort_values("PriorityScore", ascending=False)
    risk = risk.reset_index(drop=True)

    # -- Save -----------------------------------------------------------------
    out_path = f"{PROCESSED_DIR}/risk_scores.csv"
    risk.to_csv(out_path, index=False)

    print(f"\n-- Saved: {out_path}  ({len(risk):,} rows)")

    # -- Preview top RED + worsening departments ------------------------------
    print("\n-- Highest Priority Departments (RED + Worsening trend) ------------\n")
    top = risk[risk["RiskRating"] == "RED"].sort_values("PriorityScore", ascending=False).head(10)

    for _, row in top.iterrows():
        trend_arrow = "^" if row.get("TrendDirection") == "Worsening" else (
                      "v" if row.get("TrendDirection") == "Improving" else "-")
        current_val = row.get("CurrentPctOver12Weeks", float("nan"))
        peak_val    = row.get("PeakForecast", float("nan"))
        print(f"  [RED] {trend_arrow}  Current: {current_val:5.1f}%  ->  Peak forecast: {peak_val:5.1f}%")
        print(f"        {row['HealthBoardName']} | {row['SpecialtyName']} | {row['PatientType']}")
        print(f"        Trend slope: {row.get('TrendSlope', 0):+.2f} pp/month   "
              f"Net pressure: {row.get('NetPressure', 'N/A')}")
        print()

    print("-- Phase 4 Complete ----------------------------------------------------")
    print("Next: build streamlit_app/app.py (Phase 5)\n")

    return risk


if __name__ == "__main__":
    build_risk_scores()
