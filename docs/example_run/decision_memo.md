# SUNTOWER-AI retrofit portfolio memo

*Generated 2026-11-01 05:26 UTC · code 5e1a3c2 · data: sample_portfolio_fictional.csv*

> Decision-support output. All savings, emissions and reliability figures are modeled estimates from the inputs and assumptions listed; none is a measured or field-verified result. Inputs labelled SYNTHETIC are fictional and must not inform real investment.

## Decision

- Objective: maximise **NPV** (single objective; no mixed-unit score)
- CAPEX budget: **USD 60,000**; constraints: one option per site; total CAPEX <= budget; residual diesel <= 8 h/day per site (fixable scope)
- Recommended plan: **constrained_optimization** — solver status **OPTIMAL** (scipy.optimize.milp (HiGHS) scipy==1.18.1; Optimization terminated successfully. (HiGHS Status 7: Optimal))
- Retrofits: **5** of 10 valid sites; modeled CAPEX USD 59,287 (range USD 35,572–USD 83,001)
- **Cost risk:** at high-case CAPEX the plan costs USD 83,001, above the budget; re-run with CAPEX basis = high for a plan that stays within budget.
- Modeled NPV USD -2,310 (range USD -48,746 to USD 44,126); modeled CO2 avoided 39.4 t/yr

## Plans compared (identical inputs and budget)

| Plan | Status | Sites | CAPEX | NPV | CO2 t/yr | Violations |
|---|---|---:|---:|---:|---:|---|
| do_nothing | BASELINE | 0 | 0 | 0 | 0.0 | reliability (<= 8 diesel h/day): ['FICT-01', 'FICT-02', 'FICT-04', 'FICT-09', 'FICT-10'] |
| legacy_score_greedy | HEURISTIC | 2 | 41,122 | -28,054 | 20.6 | reliability (<= 8 diesel h/day): ['FICT-01', 'FICT-02', 'FICT-04', 'FICT-09', 'FICT-10'] |
| cost_benefit_greedy | HEURISTIC | 2 | 23,051 | 7,617 | 20.7 | reliability (<= 8 diesel h/day): ['FICT-01', 'FICT-04', 'FICT-09', 'FICT-10'] |
| constrained_optimization | OPTIMAL | 5 | 59,287 | -2,310 | 39.4 | none |

## Chosen investments

| Site | Option | kWp | kWh | CAPEX (range) | NPV (range) | CO2 t/yr | Diesel h/day before→after | Evidence |
|---|---|---:|---:|---|---|---:|---|---|
| FICT-01 | pv_battery | 7.8 | 6.0 | 12,453 (7,472–17,434) | -2,213 (-11,435–7,008) | 6.3 | 24.0→8.0 | SYNTHETIC |
| FICT-02 | pv_only | 8.5 | 0.0 | 10,660 (6,396–14,923) | 2,063 (-7,050–11,177) | 9.3 | 16.0→8.0 | SYNTHETIC |
| FICT-04 | pv_only | 6.0 | 0.0 | 8,400 (5,040–11,760) | -874 (-7,285–5,537) | 6.5 | 12.0→6.0 | SYNTHETIC |
| FICT-09 | pv_battery | 14.1 | 11.0 | 20,072 (12,043–28,101) | -960 (-16,627–14,706) | 11.5 | 24.0→8.0 | SYNTHETIC |
| FICT-10 | pv_only | 5.2 | 0.0 | 7,702 (4,621–10,783) | -326 (-6,350–5,699) | 5.9 | 14.1→7.0 | SYNTHETIC |

## Exclusions

- Site **FICT-11** excluded by validation: ghi_kwh_m2_day — 12.5 above maximum 8.0
- FICT-01 · battery_only: No grid to charge from (grid_hours_per_day=0)
- FICT-05 · battery_only: No diesel use to displace
- FICT-06 · pv_only: No PV space (max_pv_kwp=0)
- FICT-06 · battery_only: No grid to charge from (grid_hours_per_day=0)
- FICT-06 · pv_battery: No PV space
- FICT-07 · battery_only: No battery space (max_battery_kwh=0)
- FICT-07 · pv_battery: No battery space
- FICT-09 · battery_only: No grid to charge from (grid_hours_per_day=0)

## Evidence behind inputs

SYNTHETIC: 106, ASSUMPTION: 80, PROXY: 3, MISSING: 1

## Assumptions

- pv_performance_ratio = 0.75 fraction — Typical PR for small off-grid/hybrid PV incl. temperature and wiring losses
- battery_round_trip_eff = 0.9 fraction — Lithium-ion round-trip efficiency
- battery_depth_of_discharge = 0.8 fraction — Usable share of nominal capacity
- battery_autonomy_h = 4.0 h — Target storage autonomy at average load
- genset_kwh_per_l = 3.0 kWh/L — Same constant as legacy data_pipeline.py
- default_daytime_load_fraction = 0.5 fraction — Flat telecom load over ~12 sun hours
- discount_rate = 0.1 1/yr — Planning discount rate; replace with operator WACC
- horizon_years = 10.0 yr — Analysis horizon; battery replacement not modeled
- om_pct_capex = 0.02 1/yr — Annual O&M as share of retrofit CAPEX

## Approval

- Reviewed and approved by: ________________   Date: ____________
- Before any field decision: replace SYNTHETIC/ASSUMPTION inputs with operator or measured data, obtain vendor quotes, and re-run.
