# PURPOSE: Build Prophet time series forecasts for each Health Board + Specialty + PatientType combination, predicting PctOver12Weeks 6 months into the future.
# HOW PROPHET WORKS:
#   Prophet treats time series as: y = trend + seasonality + noise
#   We feed it (ds=Date, y=PctOver12Weeks) and it learns:
#   - Long term trend (is breach % going up or down over years?)
#   - Yearly seasonality (winter worse than summer?)
#   - It then extrapolates 6 months forward with confidence intervals
# OUTPUT:
#   data/processed/forecasts.csv - one row per future date per department
#   Columns: HBT, HealthBoardName, Specialty, SpecialtyName, PatientType,
#            ds (date), yhat (forecast), yhat_lower, yhat_upper

import pandas as pd
import numpy as np
import os
import warnings
warnings.filterwarnings("ignore")   # Prophet is verbose - suppress Stan output

from prophet import Prophet
from prophet.diagnostics import cross_validation, performance_metrics

PROCESSED_DIR = "data/processed"

# Forecasting config

FORECAST_MONTHS = 6      # how far ahead to predict
MIN_DATA_POINTS = 24     # skip a series if fewer than 24 months of history; Prophet needs enough data to learn seasonality

# Load clean data
def load_data() -> pd.DataFrame:
    path = f"{PROCESSED_DIR}/ongoing_waits_clean.csv"
    df = pd.read_csv(path, parse_dates=["Date"])
    df = df[~df["HBT"].str.startswith("RA")]   # drop hospital sub-codes

    print(f"  Loaded {len(df):,} rows")
    print(f"  Health Boards: {df['HBT'].nunique()}")
    print(f"  Specialties:   {df['Specialty'].nunique()}")
    print(f"  Patient Types: {df['PatientType'].unique()}")

    return df

# Build one Prophet model for one department
def forecast_one_series(group_df: pd.DataFrame, label: str) -> pd.DataFrame | None:
    """
    Takes a single time series (one HBT + Specialty + PatientType combination)
    and returns a DataFrame of forecasted values for the next FORECAST_MONTHS.

    Prophet requires columns named exactly 'ds' (datestamp) and 'y' (value).
    We cap y at 100 since it's a percentage - can't exceed 100%.

    Returns None if the series has too few data points to model reliably.
    """
    # Prepare Prophet input
    ts = group_df[["Date", "PctOver12Weeks"]].rename(
        columns={"Date": "ds", "PctOver12Weeks": "y"}
    ).dropna()

    # Need minimum history for Prophet to learn seasonality
    if len(ts) < MIN_DATA_POINTS:
        return None

    # Cap percentage at 100 - values slightly over 100 can occur due to
    # rounding in source data
    ts["y"] = ts["y"].clip(0, 100)

    # Remove duplicate dates (take mean if same date appears twice)
    ts = ts.groupby("ds")["y"].mean().reset_index()
    ts = ts.sort_values("ds")

    try:
        #Configure Prophet
        model = Prophet(
            yearly_seasonality=True,    # NHS data has clear winter/summer patterns
            weekly_seasonality=False,   # monthly data - no weekly pattern exists
            daily_seasonality=False,    # monthly data - no daily pattern exists
            seasonality_mode="additive",# breach % shifts by fixed amount each season
            interval_width=0.80,        # 80% confidence interval (not 95% - more useful)
            changepoint_prior_scale=0.05,  # how flexible the trend line is
                                           # 0.05 = moderate - not too rigid, not too jumpy
        )

        model.fit(ts)

        # Generate future dates 
        future = model.make_future_dataframe(
            periods=FORECAST_MONTHS,
            freq="MS"      # MS = Month Start frequency
        )

        forecast = model.predict(future)

        # Return only the future predictions (not the historical fitted values)
        future_only = forecast[forecast["ds"] > ts["ds"].max()][
            ["ds", "yhat", "yhat_lower", "yhat_upper"]
        ].copy()

        # Clip predictions to valid percentage range
        future_only["yhat"] = future_only["yhat"].clip(0, 100).round(2)
        future_only["yhat_lower"] = future_only["yhat_lower"].clip(0, 100).round(2)
        future_only["yhat_upper"] = future_only["yhat_upper"].clip(0, 100).round(2)

        return future_only

    except Exception as e:
        print(f"  [WARN] Failed to fit model for {label}: {e}")
        return None

# Run forecasts for all departments
def run_all_forecasts(df: pd.DataFrame) -> pd.DataFrame:
    """
    Loop through every unique (HBT, Specialty, PatientType) combination,
    fit a Prophet model, and collect all forecasts into one DataFrame.

    We print a progress counter because this can take a few minutes -
    there are potentially hundreds of combinations.
    """
    groups = df.groupby(["HBT", "HealthBoardName", "Specialty", "SpecialtyName", "PatientType"])

    total   = len(groups)
    done    = 0
    skipped = 0
    results = []

    print(f"\n  Fitting Prophet models for {total} department combinations")
    print(f"  (Skipping any with fewer than {MIN_DATA_POINTS} months of history)\n")

    for (hbt, hb_name, specialty, spec_name, patient_type), group in groups:
        done += 1
        label = f"{hb_name} | {spec_name} | {patient_type}"

        forecast_df = forecast_one_series(group, label)

        if forecast_df is None:
            skipped += 1
            continue

        # Tag forecast rows with their department identifiers
        forecast_df["HBT"] = hbt
        forecast_df["HealthBoardName"] = hb_name
        forecast_df["Specialty"] = specialty
        forecast_df["SpecialtyName"] = spec_name
        forecast_df["PatientType"] = patient_type

        results.append(forecast_df)

        # Progress every 50 models
        if done % 50 == 0 or done == total:
            print(f"  [{done}/{total}] Modelled: {done - skipped}  Skipped: {skipped}")

    if not results:
        print("  [ERROR] No forecasts generated")
        return pd.DataFrame()

    all_forecasts = pd.concat(results, ignore_index=True)

    # Reorder columns neatly
    col_order = [
        "HBT", "HealthBoardName", "Specialty", "SpecialtyName", "PatientType",
        "ds", "yhat", "yhat_lower", "yhat_upper"
    ]
    all_forecasts = all_forecasts[col_order]
    all_forecasts = all_forecasts.rename(columns={"ds": "ForecastDate"})

    return all_forecasts

# Main
def run_forecasts():
    print("\n Phase 3: Prophet Time Series Forecasting\n")

    print("Loading clean data")
    df = load_data()

    forecasts = run_all_forecasts(df)

    if forecasts.empty:
        print("  [ERROR] No forecasts to save")
        return

    # Save
    out_path = f"{PROCESSED_DIR}/forecasts.csv"
    forecasts.to_csv(out_path, index=False)

    print(f"\n Forecasts saved - {out_path}")
    print(f"Rows: {len(forecasts):,}")
    print(f"Departments: {forecasts.groupby(['HBT','Specialty','PatientType']).ngroups}")
    print(f"Forecast horizon: {forecasts['ForecastDate'].min().date()} - {forecasts['ForecastDate'].max().date()}")

    # Preview - which departments are forecast to breach worst?
    print("\n Top 10 Departments Forecast to Breach (6-month peak)\n")
    worst = (
        forecasts.groupby(["HealthBoardName", "SpecialtyName", "PatientType"])["yhat"]
        .max().reset_index()
        .sort_values("yhat", ascending=False)
        .head(10)
    )

    for _, row in worst.iterrows():
        if row["yhat"] > 50:
            flag = "[RED]  "
        elif row["yhat"] > 20:
            flag = "[AMBER]"
        else:
            flag = "[GREEN]"
        bar = "█" * int(row["yhat"] / 5)
        print(f"  {flag}  {row['yhat']:5.1f}%  {bar}")
        print(f"          {row['HealthBoardName']} | {row['SpecialtyName']} | {row['PatientType']}\n")

    print("Phase 3 Complete")

    return forecasts
  
if __name__ == "__main__":
    run_forecasts()
