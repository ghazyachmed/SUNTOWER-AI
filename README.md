# ☀️ SUNTOWER-AI

> **GeoAI Capital Allocation Engine for Sustainable Telecom Infrastructure**

*Not where the sun shines — where your investment shines brightest.*

---

## 🎯 Problem

ASEAN has tens of thousands of telecom towers, many dependent on diesel or unreliable grid power. Solarisation budgets are limited. **How do you decide which towers should receive investment first?**

Today, this decision is made by spreadsheet, site surveys, and vendor proposals. There is no systematic, evidence-based method to optimise capital allocation for maximum combined economic, environmental, and social impact.

## 💡 Solution

**SUNTOWER-AI** is a GeoAI capital allocation engine that fuses satellite-derived solar irradiance, tower locations, population density, terrain, and economic data to rank every telecom tower by its combined impact score.

**Give us your budget — we'll show you where your investment shines brightest.**

## 🏗️ Architecture

```
Google Earth Engine (GHI, VIIRS, SRTM, WorldCover)
          │ Feature Extraction
          ▼
Python (pandas, numpy) — Scoring Engine
          │ GeoJSON
          ▼
Streamlit + Folium — Interactive Dashboard
```

## 🚀 Quick Start

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate enriched tower data
python scripts/data_pipeline.py

# 4. Launch dashboard
streamlit run app/streamlit_app.py
```

## 📊 Features

- **Interactive Map**: Tower markers colored by SUNTOWER priority score
- **Budget Slider**: Set investment amount → see which towers are selected
- **Priority Modes**: Toggle between Balanced ESG, Economic, Carbon, or Equity
- **Custom Weights**: Fine-tune scoring criteria weights
- **Scenario Comparison**: Compare CO₂ and population impact across modes
- **Impact Curve**: Cumulative cost-benefit visualization
- **Priority Table**: Ranked tower list with all metrics
- **Export**: Download priority list as CSV

## 📁 Project Structure

```
SUNTOWER-AI/
├── app/
│   └── streamlit_app.py          # Interactive dashboard
├── scripts/
│   ├── data_pipeline.py          # Data processing pipeline
│   ├── scoring_engine.py         # Multi-criteria scoring
│   └── gee_feature_extraction.js # Google Earth Engine script
├── data/
│   └── towers_enriched.csv       # Processed tower data
├── documents source/             # Team briefing & bootcamp materials
├── requirements.txt
└── README.md
```

## 🛰️ Data Sources

| Dataset | Source | Resolution | License |
|---------|--------|:----------:|:-------:|
| Tower locations | AGAIF-provided + OpenCelliD | Point-level | CC-BY-SA 4.0 |
| Solar irradiance (GHI) | Global Solar Atlas / ERA5 via GEE | ~1km | CC-BY 4.0 |
| Population density | WorldPop 2020 | 100m | CC-BY 4.0 |
| Elevation & slope | SRTM 30m DEM | 30m | Public domain |
| Nighttime lights | VIIRS DNB | 500m | Public domain |
| Land cover | ESA WorldCover | 10m | CC-BY 4.0 |
| Road network | OpenStreetMap | Vector | ODbL |

## ⚡ Scoring Formula

```
SUNTOWER_SCORE = w₁ × Solar_Potential
              + w₂ × Energy_Savings
              + w₃ × Carbon_Avoided
              + w₄ × Connectivity_Equity
              + w₅ × Access_Feasibility
```

Weights are user-configurable via the dashboard.

## 🌏 ASEAN GeoAI Fusion 2026

**Team**: HACK-ID-068
**Theme**: ESG — Environmental, Social, and Governance
**Hackathon**: ASEAN GeoAI Fusion 2026 by MCMC

---

*Built for the ASEAN GeoAI Fusion 2026 Hackathon*
