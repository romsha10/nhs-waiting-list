# nhs-waiting-list
Predictive waiting list dashboard for NHS Scotland using Prophet and Streamlit
# NHS Scotland Waiting Times Risk Dashboard

A predictive analytics pipeline that monitors NHS Scotland waiting times,
forecasts 12-week TTG breach risk using Facebook Prophet, and presents
findings through an interactive Streamlit dashboard and Power BI report.

---

## Live Dashboard

[View on Streamlit Cloud](https://YOUR_USERNAME-nhs-waiting-list.streamlit.app)

---

## Project Structure
nhs-waiting-list/

├── data/

│   ├── raw/                          # Downloaded from NHS Scotland API

│   └── processed/                    # Cleaned and modelled outputs

│       ├── ongoing_waits_clean.csv

│       ├── monthly_waits_clean.csv

│       ├── additions_removals_clean.csv

│       ├── forecasts.csv

│       └── risk_scores.csv

├── src/

│   ├── fetch_data.py                 # Phase 1 — NHS API download

│   ├── clean_data.py                 # Phase 2 — Pandas cleaning pipeline

│   ├── forecast.py                   # Phase 3 — Prophet forecasting

│   └── risk_engine.py               # Phase 4 — Traffic light risk scoring

├── streamlit_app/

│   └── app.py                        # Phase 5 — Interactive dashboard

├── powerbi/

│   └── nhs_dashboard.pbix            # Phase 6 — Power BI report

├── outputs/

│   └── executive_brief.md            # Phase 7 — Board executive brief

├── requirements.txt

└── README.md

---

## Key Findings

| Risk Rating | Departments | Percentage |
|---|---|---|
| RED — Breach Predicted | 515 | 56.2% |
| AMBER — At Risk | 247 | 27.0% |
| GREEN — On Target | 154 | 16.8% |

Over 56% of monitored NHS Scotland departments are forecast to breach
the 12-week Treatment Time Guarantee within the next 6 months.

---

## How It Works

### Phase 1 — Data
Pulls live data from NHS Scotland Open Data (opendata.nhs.scot) via
the CKAN API. No scraping. Official government data, updated monthly.
330,000+ rows covering October 2012 to present.

### Phase 2 — Cleaning
Pandas pipeline parses NHS date formats, drops quality flag columns,
maps health board and specialty codes to human-readable names, and
calculates the core breach metric — percentage of patients waiting
over 12 weeks per department.

### Phase 3 — Forecasting
A separate Facebook Prophet model is fitted for each Health Board,
Specialty and Patient Type combination (916 models total). Prophet
learns long-term trend and yearly seasonality from 13 years of data
and projects 6 months forward with 80% confidence intervals.

### Phase 4 — Risk Engine
Each department receives a RAG rating based on peak forecasted breach
percentage. A Priority Score combines RAG rating with trend direction
(linear slope over last 6 months) to rank departments by urgency.

### Phase 5 — Streamlit App
Four-page interactive dashboard built with Streamlit and Plotly:
- National Overview — KPIs, donut chart, priority table
- Health Board Drill-Down — specialty breakdown per board
- Specialty Deep Dive — full forecast chart with confidence intervals
- About — methodology and data sources

### Phase 6 — Power BI
Three-page executive dashboard for NHS managers:
- Executive Summary - national RAG overview
- Health Board Drill-Down - slicers for board and specialty
- Forecast View - 6-month forecast with threshold lines

---

## Traffic Light System

| Rating | Threshold | Meaning |
|---|---|---|
| GREEN | Below 20% | Comfortably within TTG target |
| AMBER | 20% to 50% | At risk — monitoring recommended |
| RED | Above 50% | Breach predicted - action required |

Ratings based on PEAK forecasted breach percentage over next 6 months.
Priority Score adds trend direction - RED plus worsening trend = highest urgency.

---

## Tech Stack

| Tool | Purpose |
|---|---|
| Python 3.10+ | Core language |
| Pandas | Data cleaning and transformation |
| Facebook Prophet | Time series forecasting |
| Streamlit | Interactive web dashboard |
| Plotly | Charts and visualisations |
| Power BI | Executive manager dashboard |
| NHS Scotland Open Data | Official data source |
| GitHub | Version control and deployment |

---

## Setup and Run

# Clone the repo
git clone https://github.com/YOUR_USERNAME/nhs-waiting-list.git
cd nhs-waiting-list

# Create virtual environment
python -m venv venv

# Activate — Windows
venv\Scripts\activate

# Activate — Mac/Linux
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the full pipeline
python src/fetch_data.py
python src/clean_data.py
python src/forecast.py
python src/risk_engine.py

# Launch the dashboard
streamlit run streamlit_app/app.py


---

## Data Source

NHS Scotland Stage of Treatment Waiting Times
Published by Public Health Scotland
Source: opendata.nhs.scot
Licence: UK Open Government Licence (OGL)
Updated: Monthly

---

## Limitations

- Small Health Boards (Orkney, Shetland, Western Isles) have low patient
  volumes so percentage metrics are more volatile and less reliable
- Forecasts assume historical patterns continue — major policy changes
  or events such as COVID will reduce accuracy
- This tool is for monitoring and early warning only, not clinical decisions

---

## Authors

Built as a portfolio project demonstrating predictive analytics applied
to real NHS Scotland open data.
