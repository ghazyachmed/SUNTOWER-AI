# SENO baseline audit: SUNTOWER-AI before the portfolio extension

Audit date: 2026-11-01. Branch audited: `main` at `46a2f0c10c0384bf2a236b9a5a77be87b4973010` ("Initial commit"). The working tree was clean. This document records what the code and data show. It does not judge the idea behind the project.

## 1. Reproduction record

| Item | Value |
|---|---|
| Platform | macOS, Darwin 25.6.0, arm64 |
| Python | system `/usr/bin/python3` 3.9.6 has none of the dependencies. A venv was built with Homebrew Python 3.12.13 |
| Packages (venv) | streamlit 1.66.1, pandas 3.1.0, numpy 2.5.4, folium 0.20.0, streamlit-folium 0.27.4, branca 0.8.2, scikit-learn 1.9.1, plotly 7.1.0, scipy 1.18.1, pytest 9.2.0 |
| `requirements.txt` | Lower bounds only (`>=`). There is no lock file, so other installs may resolve different versions |
| Pipeline input | `documents source/sources/bootcamp 2/GeoAI Dataset/lokasi_menara_telekomunikasi.csv` (3,547 rows) |
| Command | `process_tower_data(input, <scratch>/repro_enriched.csv)`. It was written to a scratch path so the committed CSV was not overwritten |
| Result | 3,532 rows. Every numeric column matches the committed `data/towers_enriched.csv` exactly (max abs diff 0.0) |
| App | `streamlit.testing.AppTest` ran `app/streamlit_app.py` with no exceptions |
| Tests before | None existed |

Pipeline console output (abridged):
```
Loaded 3547 towers
⚠ Detected 305 rows with swapped lat/lon — auto-correcting
⚠ Removing 15 rows with invalid coordinates
Lat range: -6.9742 to -5.8953   Lon range: 107.5496 to 107.7362
GHI range 5.06 - 5.46;  Strong Grid: 3531 (100.0%), Off-Grid: 1
```

Legacy scoring at the default `balanced` weights, with the `candidates_only=False` path the app uses:

| Budget | Rows selected | Grid class of selected | Modeled savings/yr | "Population served" | Payback |
|---|---|---|---|---|---|
| USD 500k | 20 | 20 × Strong Grid | USD 21,121 | 51,269,750 | 23.7 yr |
| USD 2M | 80 | 80 × Strong Grid | USD 84,485 | 205,124,893 | 23.7 yr |

## 2. Claim-to-evidence ledger

| # | Claim (where) | What the code or data actually show | Status |
|---|---|---|---|
| C1 | "fuses satellite-derived solar irradiance, tower locations, population density, terrain, and economic data" (README) | `data_pipeline.py` reads only the tower CSV. GHI, elevation, population, night lights, road distance, grid status, energy, cost and CO2 all come from closed-form formulas, some with `sin`/`cos` "noise" terms. No satellite data is read | **Not supported.** Relabelled `modeled_proxy` |
| C2 | Architecture "Google Earth Engine → Feature Extraction → Python" (README) | `gee_feature_extraction.js` is a stand-alone demo on 5 inline points. Nothing in the repo shows its output being exported or consumed. No GEE-derived file exists | Not supported (script exists, never integrated) |
| C3 | Data-source table: Global Solar Atlas/ERA5, WorldPop, SRTM, VIIRS, WorldCover, OSM, OpenCelliD (README) | None of these datasets is present or used by Python code. The tower data is a Bandung municipal inventory, not OpenCelliD (an unused `502.csv` OpenCelliD-format file covers Malaysia, MCC 502) | Not supported; licences checked separately in `DATA_RIGHTS.md` |
| C4 | "Budget-constrained optimization" (scoring_engine docstring, app methodology) | `budget_allocation` sorts by score and keeps the prefix whose cumulative sum is ≤ budget. It stops at the first tower that does not fit, never tries cheaper towers, and has no optimality property | Mislabelled: heuristic, not optimisation |
| C5 | "GeoAI" / AI | No model is trained anywhere. Scores are min-max normalised weighted sums | No predictive AI present |
| C6 | "Population Served" metric (app) | Sum of overlapping 5-km population proxies. 80 towers "serve" 205 M people, about 4× West Java's population | **Wrong as stated.** Removed from new outputs; the legacy tab relabels it |
| C7 | "Off-Grid Towers" / candidate filtering | 3,531 of 3,532 rows are "Strong Grid". The app passes `candidates_only=False`, so it selects strong-grid towers with 23.7-year modeled payback | Proxy classification is not informative for this city dataset |
| C8 | 3,532 "towers" | The source has `tahun` = 2017–2020 (667–975 rows per year). The same inventory is listed per year: 2,886 rows share coordinates with another row, up to 8 per point. The pipeline drops `tahun` | Unique physical towers ≈ 1,000 (not deduplicated; flagged) |
| C9 | Coordinate cleaning | 305 rows auto-swapped. One Coblong row has lat −5.895, about 110 km north in the Java Sea, which looks like a −6.895 typo; it passes the bounds check. One row at lat +6.94 is dropped | Partly silent; documented |
| C10 | Savings, CO2 and payback figures | Formula outputs from uncited constants (diesel USD 0.82/L, tariff 0.08, grid EF 0.76, solar offset 0.70, flat CAPEX 25k/45k) | Modeled estimates only |
| C11 | Attribution to ASEAN GeoAI Fusion 2026 / HACK-ID-068 | Present in README and app | Preserved |

## 3. Data rights of the legacy inputs

- `lokasi_menara_telekomunikasi.csv` contains tower owner names, street addresses and exact coordinates for Kota Bandung. Its schema (BPS/Kemendagri codes, `satuan`, `tahun`) matches Indonesian regional open-data portals. It arrived with the AGAIF bootcamp materials. **The publisher licence has not been verified**, so the new demo uses fictional towers only. See `DATA_RIGHTS.md`.
- The repo also redistributes bootcamp PDFs, notebooks, shapefiles and an OpenCelliD-format extract (`502.csv`). Redistribution rights are not stated. They are listed as a risk; nothing was removed.

## 4. Assumptions isolated for the extension

All new estimates take inputs from a typed schema with per-field evidence labels (`scripts/site_schema.py`). Engineering and finance assumptions sit in one table (`retrofit_options.ASSUMPTIONS`), which the UI and memo print. The legacy constants above are reused only as labelled `assumption` rows in the fictional sample.

## 5. What was left unchanged

`data/towers_enriched.csv`, the pipeline formulas, `scoring_engine.py` and all source documents are unchanged. The only edit to the pipeline is a docstring evidence note. The legacy flow is still reachable from the app's "Legacy screening map" tab and is used as the `legacy_score_greedy` baseline.
