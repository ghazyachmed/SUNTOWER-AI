# TKT self-assessment (informal)

Reference framework: Indonesia's Tingkat Kesiapterapan Teknologi (TKT), Permenristekdikti No. 42/2016. **This is a team self-assessment against the TKT level descriptions. It is not an official TKT designation.** An official level requires the formal measurement process (for example the Kemdikbudristek/BRIN TKT measurement instrument) and an assessor. The indicator wording below is paraphrased.

Assessment date: 2026-11-01, branch `feat/seno-portfolio-decision`.

## Evidence by level

| Level | What the level asks for (paraphrased) | Evidence in this repo | Assessment |
|---|---|---|---|
| TKT 1 | Basic principles observed and reported | Problem framing (telecom tower energy retrofits under CAPEX limits); energy and finance formulas documented in `retrofit_options.FORMULAS` | Met |
| TKT 2 | Technology concept and application formulated | Multiple-choice knapsack formulation, evidence-labelled schema, four-plan comparison (`portfolio_optimizer.py` docstring) | Met |
| TKT 3 | Analytical and experimental proof of concept of key functions | Working code paths: validation → option estimates → MILP → baselines → memo, checked by 64 automated tests. These include brute-force optimality checks on 25 random instances and exact-fit, infeasible, zero-cost, tie, variant, duplicate-tower and uncertain-cost cases (`docs/SENO_EXECUTION_EVIDENCE.md`). **All portfolio inputs are fictional or modeled** | **Plausible for the software decision method only.** Not for any energy-savings claim |
| TKT 4 | Components validated together in a laboratory environment | Components are integrated in the app and CLI on a fictional 11-tower portfolio. No real operator data, no comparison against measured site energy, no independent review | Not met. Integration exists, but validation against real inputs does not |
| TKT 5 | Validation in a relevant (simulated operational) environment | None. Would need operator-supplied site data (loads, diesel logs, tariffs, quotes) on a real portfolio, with results reviewed by planners | Not met |
| TKT 6 | Demonstration of a prototype in a relevant environment | None. Would need a pilot with a TowerCo planning cycle and before/after metering | Not met |

## Predictive AI (Phase 3)

The prediction target is daily site energy consumption. The interface, label contract and leakage-resistant evaluation (temporal cut-off plus held-out sites, against a moving-average baseline) are implemented in `scripts/energy_forecast.py`. They run only on a **synthetic** panel in a unit test. ML is **PLANNED, not demonstrated**, and contributes no TKT evidence.

## What would move the evidence up

1. Get operator-supplied or measured data for 8–12 real sites under a data-sharing agreement: load, diesel logs, grid hours, tariffs, quotes. Re-run, keeping the labels.
2. Have TowerCo planners review the plan comparison and memo against their current method. Record the outcome.
3. With historical meter data, train and evaluate the forecast model, then check whether it changes portfolio decisions compared with the deterministic estimates.
4. After installation, compare modeled with metered diesel and energy savings at pilot sites.
