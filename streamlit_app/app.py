# PURPOSE: Interactive public dashboard for NHS Scotland waiting time risk
#          Built with Streamlit - runs locally and deploys free on Streamlit Cloud
#
# PAGES:
#   1. National Overview   - traffic light summary across all boards
#   2. Health Board Drill  - pick a board, see all its specialties
#   3. Specialty Deep Dive - full forecast chart for one department
#   4. About               - methodology and data sources

import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import os
import sys

# Page config - must be first Streamlit call

st.set_page_config(
    page_title="NHS Scotland Waiting Times Risk Dashboard",
    page_icon="images/nhs_logo.png" if os.path.exists("images/nhs_logo.png") else ":hospital:",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Paths - work whether run from repo root or streamlit_app/
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROCESSED = os.path.join(ROOT, "data", "processed")

# Load data - cached so it only reads CSV once per session
@st.cache_data
def load_risk():
    return pd.read_csv(os.path.join(PROCESSED, "risk_scores.csv"))

@st.cache_data
def load_ongoing():
    df = pd.read_csv(os.path.join(PROCESSED, "ongoing_waits_clean.csv"), parse_dates=["Date"])
    return df

@st.cache_data
def load_forecasts():
    df = pd.read_csv(os.path.join(PROCESSED, "forecasts.csv"), parse_dates=["ForecastDate"])
    return df

# Colour helpers
COLOURS = {
    "RED":   "#E63946",
    "AMBER": "#F4A261",
    "GREEN": "#2A9D8F",
}

def rag_badge(rating: str) -> str:
    """Return an HTML coloured badge for a RAG rating."""
    colour = COLOURS.get(rating, "#888")
    return f'<span style="background:{colour};color:white;padding:2px 10px;border-radius:4px;font-weight:bold">{rating}</span>'

# Sidebar navigation
st.sidebar.title("NHS Scotland")
st.sidebar.caption("Waiting Times Risk Dashboard")
st.sidebar.markdown("---")

page = st.sidebar.radio(
    "Navigate",
    ["National Overview", "Health Board Drill-Down", "Specialty Deep Dive", "About"],
)

st.sidebar.markdown("---")
st.sidebar.caption(
    "Data: [NHS Scotland Open Data](https://www.opendata.nhs.scot)  \n"
    "Updated: Monthly  \n"
    "Forecast horizon: 6 months  \n"
    "Model: Facebook Prophet"
)

# Load all data upfront
risk = load_risk()
ongoing   = load_ongoing()
forecasts = load_forecasts()

latest_data_date = ongoing["Date"].max()
forecast_end = forecasts["ForecastDate"].max()

# PAGE 1 - National Overview
if page == "National Overview":

    st.title("NHS Scotland - Waiting Times Risk Dashboard")
    st.caption(
        f"Actual data to {latest_data_date.strftime('%B %Y')}  |  "
        f"Forecast to {pd.to_datetime(forecast_end).strftime('%B %Y')}  |  "
        f"12-week Treatment Time Guarantee (TTG) monitoring"
    )

    # KPI row
    total = len(risk)
    n_red   = (risk["RiskRating"] == "RED").sum()
    n_amber = (risk["RiskRating"] == "AMBER").sum()
    n_green = (risk["RiskRating"] == "GREEN").sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Departments Monitored", f"{total:,}")
    c2.metric("RED - Breach Predicted",  f"{n_red}",   delta=None)
    c3.metric("AMBER - At Risk",         f"{n_amber}", delta=None)
    c4.metric("GREEN - On Target",       f"{n_green}", delta=None)

    st.markdown("---")

    # RAG donut chart + bar chart side by side
    col_left, col_right = st.columns([1, 2])

    with col_left:
        st.subheader("Risk Distribution")
        fig_donut = go.Figure(go.Pie(
            labels=["RED", "AMBER", "GREEN"],
            values=[n_red, n_amber, n_green],
            hole=0.55,
            marker_colors=[COLOURS["RED"], COLOURS["AMBER"], COLOURS["GREEN"]],
            textinfo="label+percent",
            showlegend=False,
        ))
        fig_donut.update_layout(
            height=300, margin=dict(t=10, b=10, l=10, r=10),
            annotations=[dict(text=f"{n_red}<br>RED", x=0.5, y=0.5,
                              font_size=18, showarrow=False)]
        )
        st.plotly_chart(fig_donut, use_container_width=True)

    with col_right:
        st.subheader("Risk by Health Board")
        # Count RED/AMBER/GREEN per board, exclude national aggregate
        board_risk = risk[risk["HBT"] != "S92000003"].copy()
        board_counts = (
            board_risk.groupby(["HealthBoardName", "RiskRating"])
            .size().reset_index(name="Count")
        )
        fig_bar = px.bar(
            board_counts,
            x="HealthBoardName", y="Count", color="RiskRating",
            color_discrete_map=COLOURS,
            category_orders={"RiskRating": ["RED", "AMBER", "GREEN"]},
            labels={"HealthBoardName": "", "Count": "Departments"},
        )
        fig_bar.update_layout(
            height=300, margin=dict(t=10, b=10),
            xaxis_tickangle=-35, legend_title="",
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("---")

    # Highest priority departments table
    st.subheader("Highest Priority Departments - Action Required")
    st.caption("Sorted by Priority Score (RED + worsening trend ranked highest)")

    top_risk = risk[risk["RiskRating"] == "RED"].sort_values(
        "PriorityScore", ascending=False
    ).head(20)[[
        "HealthBoardName", "SpecialtyName", "PatientType",
        "RiskRating", "CurrentPctOver12Weeks", "PeakForecast",
        "TrendDirection", "TrendSlope", "NumberWaiting"
    ]].copy()

    top_risk.columns = [
        "Health Board", "Specialty", "Patient Type",
        "Risk", "Current %", "Peak Forecast %",
        "Trend", "Slope (pp/mo)", "Patients Waiting"
    ]
    top_risk["Current %"]       = top_risk["Current %"].round(1)
    top_risk["Peak Forecast %"] = top_risk["Peak Forecast %"].round(1)

    st.dataframe(
        top_risk,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Risk": st.column_config.TextColumn("Risk"),
            "Current %": st.column_config.NumberColumn("Current %", format="%.1f%%"),
            "Peak Forecast %": st.column_config.NumberColumn("Peak Forecast %", format="%.1f%%"),
            "Patients Waiting": st.column_config.NumberColumn(format="%d"),
        }
    )

    # National trend chart
    st.markdown("---")
    st.subheader("NHS Scotland - National Breach Trend")
    st.caption("All specialties combined (Z9), both patient types")

    national = ongoing[
        (ongoing["HBT"] == "S92000003") &
        (ongoing["Specialty"] == "Z9")
    ].sort_values("Date")

    national_fc = forecasts[
        (forecasts["HBT"] == "S92000003") &
        (forecasts["Specialty"] == "Z9")
    ].sort_values("ForecastDate")

    if not national.empty:
        fig_nat = go.Figure()

        for pt, colour in [("New Outpatient", "#264653"), ("Inpatient/Day case", "#E76F51")]:
            sub = national[national["PatientType"] == pt]
            fig_nat.add_trace(go.Scatter(
                x=sub["Date"], y=sub["PctOver12Weeks"],
                name=f"{pt} (Actual)",
                line=dict(color=colour, width=2),
            ))
            # Forecast
            sub_fc = national_fc[national_fc["PatientType"] == pt]
            if not sub_fc.empty:
                fig_nat.add_trace(go.Scatter(
                    x=sub_fc["ForecastDate"], y=sub_fc["yhat"],
                    name=f"{pt} (Forecast)",
                    line=dict(color=colour, width=2, dash="dash"),
                ))
                # Confidence band
                fig_nat.add_trace(go.Scatter(
                    x=pd.concat([sub_fc["ForecastDate"], sub_fc["ForecastDate"][::-1]]),
                    y=pd.concat([sub_fc["yhat_upper"], sub_fc["yhat_lower"][::-1]]),
                    fill="toself",
                    fillcolor="rgba(38,70,83,0.12)" if pt == "New Outpatient" else "rgba(231,111,81,0.12)",
                    line=dict(color="rgba(0,0,0,0)"),
                    showlegend=False, name="Confidence",
                ))

        fig_nat.add_hline(y=20, line_dash="dot", line_color=COLOURS["AMBER"],
                          annotation_text="AMBER threshold (20%)")
        fig_nat.add_hline(y=50, line_dash="dot", line_color=COLOURS["RED"],
                          annotation_text="RED threshold (50%)")

        fig_nat.update_layout(
            height=400,
            xaxis_title="Date",
            yaxis_title="% Waiting Over 12 Weeks",
            yaxis=dict(range=[0, 105]),
            legend=dict(orientation="h", yanchor="bottom", y=1.02),
            margin=dict(t=40, b=40),
        )
        st.plotly_chart(fig_nat, use_container_width=True)

# PAGE 2 - Health Board Drill-Down
elif page == "Health Board Drill-Down":

    st.title("Health Board Drill-Down")

    # Filter to real health boards only
    boards = sorted(
        risk[~risk["HBT"].str.startswith(("RA", "SB", "S92"))]
        ["HealthBoardName"].unique()
    )

    selected_board = st.selectbox("Select Health Board", boards)
    board_data = risk[risk["HealthBoardName"] == selected_board]

    if board_data.empty:
        st.warning("No data for this board.")
        st.stop()

    # Board-level KPIs
    b1, b2, b3, b4 = st.columns(4)
    b1.metric("Specialties Monitored", len(board_data))
    b2.metric("RED",   (board_data["RiskRating"] == "RED").sum())
    b3.metric("AMBER", (board_data["RiskRating"] == "AMBER").sum())
    b4.metric("GREEN", (board_data["RiskRating"] == "GREEN").sum())

    st.markdown("---")

    # Patient type filter
    pt_filter = st.radio(
        "Patient Type", ["All", "New Outpatient", "Inpatient/Day case"],
        horizontal=True
    )
    if pt_filter != "All":
        board_data = board_data[board_data["PatientType"] == pt_filter]

    # Specialty risk table
    st.subheader(f"All Specialties - {selected_board}")

    display = board_data[[
        "SpecialtyName", "PatientType", "RiskRating",
        "CurrentPctOver12Weeks", "PeakForecast",
        "TrendDirection", "TrendSlope", "NumberWaiting"
    ]].sort_values("PeakForecast", ascending=False).copy()

    display.columns = [
        "Specialty", "Patient Type", "Risk",
        "Current %", "Peak Forecast %",
        "Trend", "Slope (pp/mo)", "Patients Waiting"
    ]

    st.dataframe(
        display,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Current %": st.column_config.NumberColumn(format="%.1f%%"),
            "Peak Forecast %": st.column_config.NumberColumn(format="%.1f%%"),
            "Patients Waiting": st.column_config.NumberColumn(format="%d"),
        }
    )

    # Horizontal bar chart of peak forecast by specialty
    st.subheader("Peak Forecast Breach % by Specialty")

    fig_hbar = px.bar(
        display.sort_values("Peak Forecast %"),
        x="Peak Forecast %", y="Specialty",
        color="Risk",
        color_discrete_map=COLOURS,
        orientation="h",
        text="Peak Forecast %",
        labels={"Peak Forecast %": "Predicted Peak % Over 12 Weeks"},
    )
    fig_hbar.update_traces(texttemplate="%{text:.1f}%", textposition="outside")
    fig_hbar.add_vline(x=20, line_dash="dot", line_color=COLOURS["AMBER"])
    fig_hbar.add_vline(x=50, line_dash="dot", line_color=COLOURS["RED"])
    fig_hbar.update_layout(
        height=max(400, len(display) * 25),
        margin=dict(t=20, b=20),
        showlegend=True,
        yaxis_title="",
    )
    st.plotly_chart(fig_hbar, use_container_width=True)

# PAGE 3 - Specialty Deep Dive
elif page == "Specialty Deep Dive":

    st.title("Specialty Deep Dive - Forecast Chart")
    st.caption("Full historical trend + 6-month Prophet forecast with confidence intervals")

    col1, col2, col3 = st.columns(3)

    boards_list = sorted(
        ongoing[~ongoing["HBT"].str.startswith(("RA", "SB", "S92"))]
        ["HealthBoardName"].dropna().unique()
    )
    selected_board = col1.selectbox("Health Board", boards_list)

    board_specs = sorted(
        ongoing[ongoing["HealthBoardName"] == selected_board]
        ["SpecialtyName"].dropna().unique()
    )
    selected_spec = col2.selectbox("Specialty", board_specs)

    pt_opts = sorted(
        ongoing[
            (ongoing["HealthBoardName"] == selected_board) &
            (ongoing["SpecialtyName"] == selected_spec)
        ]["PatientType"].dropna().unique()
    )
    selected_pt = col3.selectbox("Patient Type", pt_opts)

    # Get actual data
    actual = ongoing[
        (ongoing["HealthBoardName"] == selected_board) &
        (ongoing["SpecialtyName"]   == selected_spec) &
        (ongoing["PatientType"]     == selected_pt)
    ].sort_values("Date")

    # Get forecast data
    fc = forecasts[
        (forecasts["HealthBoardName"] == selected_board) &
        (forecasts["SpecialtyName"]   == selected_spec) &
        (forecasts["PatientType"]     == selected_pt)
    ].sort_values("ForecastDate")

    # Get risk score
    rs = risk[
        (risk["HealthBoardName"] == selected_board) &
        (risk["SpecialtyName"]   == selected_spec) &
        (risk["PatientType"]     == selected_pt)
    ]

    if actual.empty:
        st.warning("No data found for this combination.")
        st.stop()

    # Risk badge
    if not rs.empty:
        rating = rs.iloc[0]["RiskRating"]
        peak   = rs.iloc[0]["PeakForecast"]
        trend  = rs.iloc[0].get("TrendDirection", "Unknown")
        current_pct = rs.iloc[0].get("CurrentPctOver12Weeks", float("nan"))

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Risk Rating",         rating)
        m2.metric("Current Breach %",    f"{current_pct:.1f}%")
        m3.metric("Peak Forecast %",     f"{peak:.1f}%")
        m4.metric("Trend",               trend)

    st.markdown("---")

    # Main forecast chart
    fig = go.Figure()

    # Actual historical line
    fig.add_trace(go.Scatter(
        x=actual["Date"],
        y=actual["PctOver12Weeks"],
        name="Actual",
        line=dict(color="#264653", width=2.5),
        mode="lines+markers",
        marker=dict(size=4),
    ))

    if not fc.empty:
        # Forecast line
        fig.add_trace(go.Scatter(
            x=fc["ForecastDate"],
            y=fc["yhat"],
            name="Forecast (Prophet)",
            line=dict(color="#E76F51", width=2.5, dash="dash"),
        ))

        # Confidence interval shading
        fig.add_trace(go.Scatter(
            x=pd.concat([fc["ForecastDate"], fc["ForecastDate"][::-1]]),
            y=pd.concat([fc["yhat_upper"], fc["yhat_lower"][::-1]]),
            fill="toself",
            fillcolor="rgba(231,111,81,0.15)",
            line=dict(color="rgba(0,0,0,0)"),
            name="80% Confidence Interval",
        ))

    # Threshold lines
    fig.add_hline(y=20, line_dash="dot", line_color=COLOURS["AMBER"],
                  annotation_text="AMBER (20%)", annotation_position="top left")
    fig.add_hline(y=50, line_dash="dot", line_color=COLOURS["RED"],
                  annotation_text="RED (50%)", annotation_position="top left")

    # Vertical line at forecast start
    if not actual.empty:
        fig.add_vline(
            x=actual["Date"].max(),
            line_dash="dash", line_color="#aaa",
            annotation_text="Forecast starts",
        )

    fig.update_layout(
        title=f"{selected_board} - {selected_spec} ({selected_pt})",
        xaxis_title="Date",
        yaxis_title="% Waiting Over 12 Weeks",
        yaxis=dict(range=[0, 105]),
        height=500,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        margin=dict(t=60, b=40),
    )
    st.plotly_chart(fig, use_container_width=True)

    # Wait distribution table
    st.subheader("Recent Data")
    recent_table = actual.tail(12)[[
        "Date", "NumberWaiting", "NumberWaitingOver12Weeks",
        "PctOver12Weeks", "Median", "90thPercentile"
    ]].copy()
    recent_table["Date"] = recent_table["Date"].dt.strftime("%b %Y")
    recent_table.columns = [
        "Month", "Total Waiting", "Waiting Over 12 Weeks",
        "% Over 12 Weeks", "Median Wait (weeks)", "90th Pct Wait (weeks)"
    ]
    st.dataframe(recent_table, use_container_width=True, hide_index=True)

# PAGE 4 - About
elif page == "About":

    st.title("About This Dashboard")

    st.markdown("""
    ## What is this?

    This dashboard monitors NHS Scotland waiting times and predicts which
    departments are at risk of breaching the 12-week Treatment Time Guarantee (TTG)
    before the breach occurs - giving managers time to act.

    ## Data Source

    All data comes from [NHS Scotland Open Data](https://www.opendata.nhs.scot),
    specifically the **Stage of Treatment Waiting Times** dataset published monthly
    by Public Health Scotland. Data runs from October 2012 to present.

    ## Methodology

    **Step 1 - Data Pipeline**
    Raw waiting time counts are downloaded via the NHS Scotland CKAN API,
    cleaned with Pandas, and structured by Health Board, Specialty, and Patient Type.

    **Step 2 - Forecasting**
    A separate Facebook Prophet model is fitted for each department combination
    (Health Board x Specialty x Patient Type). Prophet decomposes the time series
    into trend + yearly seasonality, then extrapolates 6 months forward with
    80% confidence intervals.

    **Step 3 - Traffic Light Classification**
    Each department receives a RAG rating based on its peak forecasted breach
    percentage over the next 6 months:

    | Rating | Threshold | Meaning |
    |--------|-----------|---------|
    | GREEN  | < 20%     | Comfortably within TTG target |
    | AMBER  | 20 - 50%  | At risk - monitoring recommended |
    | RED    | > 50%     | Breach predicted - action required |

    **Step 4 - Priority Score**
    A composite score combining RAG rating and trend direction ranks departments
    by urgency. RED + worsening trend = highest priority.

    ## Limitations

    - Small Health Boards (Orkney, Shetland, Western Isles) have very low patient
      volumes, so percentage metrics are more volatile and less reliable.
    - Forecasts assume historical patterns continue. Major policy changes or
      events (e.g. COVID) will reduce accuracy.
    - This tool is for monitoring and early warning only - not for clinical decisions.

    ## Built With

    Python · Pandas · Facebook Prophet · Streamlit · Plotly · NHS Scotland Open Data

    ---
    *Built as a portfolio project demonstrating predictive analytics applied to
    real NHS Scotland open data.*
    """)
