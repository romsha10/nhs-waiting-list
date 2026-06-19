# NHS Scotland Waiting Times - Executive Brief
**Prepared for:** NHS Scotland Board  
**Date:** June 2026  
**Subject:** Predictive Analysis of 12-Week TTG Breach Risk Across NHS Scotland

---

## Situation

NHS Scotland is operating under sustained pressure across inpatient, day case,
and outpatient services. As of March 2026, analysis of Public Health Scotland
open data reveals that the majority of monitored department combinations are
either breaching or forecast to breach the 12-week Treatment Time Guarantee.

---

## Key Findings

**916 department combinations monitored** across 17 Health Boards and 55
specialties, covering both New Outpatient and Inpatient/Day Case patient types.

| Risk Rating | Departments | % of Total |
|---|---|---|
| RED — Breach Predicted | 515 | 56.2% |
| AMBER — At Risk | 247 | 27.0% |
| GREEN — On Target | 154 | 16.8% |

Over 56% of all monitored departments are forecast to breach the 12-week TTG
within the next 6 months. Only 1 in 6 departments is currently on target.

---

## Highest Risk Areas

The following departments are classified RED with a worsening trend -
meaning breach rates are actively accelerating:

| Health Board | Specialty | Current Breach % | Forecast Peak % | Trend |
|---|---|---|---|---|
| NHS Lanarkshire | Specialty AG | 58.6% | 73.4% | Worsening |
| NHS Fife | Neurosurgery | 63.4% | 84.8% | Worsening |
| NHS Ayrshire & Arran | Specialty A9 | 66.5% | 83.4% | Worsening |
| NHS Highland | Gynaecology | 59.7% | 64.9% | Worsening |
| NHS Fife | Specialty CB | 53.9% | 69.5% | Worsening |

NHS Lanarkshire Specialty AG is trending at +8.56 percentage points per month —
without intervention, a full breach is projected within 2 months.

---

## Forecast Methodology

A separate time series model (Facebook Prophet) was fitted for each department
combination using 13 years of monthly Public Health Scotland data (October 2012
to March 2026). Prophet decomposes each series into long-term trend and yearly
seasonality, then projects 6 months forward with 80% confidence intervals.

Traffic light classification is applied to the peak forecasted breach percentage:

- GREEN: peak forecast below 20%
- AMBER: peak forecast between 20% and 50%
- RED: peak forecast above 50%

A Priority Score combining RAG rating and trend direction ranks departments
by urgency for operational response.

---

## Structural Pressure

Analysis of quarterly additions and removals data reveals that several boards
are adding patients to waiting lists faster than they are removing them —
a structural imbalance that will sustain or worsen breach rates regardless
of short-term capacity measures.

NHS Ayrshire & Arran shows net positive pressure of +410 patients per quarter
in affected specialties. This indicates demand is outpacing capacity at a
systemic level, not just operationally.

---

## Recommendations

**Immediate (0-3 months)**
- Direct additional capacity to NHS Lanarkshire AG, NHS Fife Neurosurgery,
  and NHS Ayrshire & Arran A9 — all RED with accelerating trend slopes
- Initiate weekly breach monitoring for all RED + Worsening departments
- Review patient pathway efficiency in Gynaecology across Highland and Western Isles

**Short Term (3-6 months)**
- Address structural additions/removals imbalance in boards with positive
  net pressure — capacity planning must account for demand growth rate
- Extend predictive monitoring to AMBER departments showing upward trend slopes
- Commission specialty-level deep dive into Neurosurgery and Ophthalmology
  which show system-wide pressure across multiple boards

**Strategic (6-12 months)**
- Embed this predictive tool into monthly NHS Board performance reporting
- Integrate with workforce and theatre capacity data for root cause analysis
- Establish AMBER as the intervention threshold, not RED — by the time
  a department reaches RED, meaningful lead time for action has been lost

---

## Data Source

All analysis based on NHS Scotland Stage of Treatment Waiting Times dataset,
published monthly by Public Health Scotland via opendata.nhs.scot under
UK Open Government Licence. Data covers October 2012 to March 2026.
916 Prophet models fitted. Total dataset: 330,000+ rows.
