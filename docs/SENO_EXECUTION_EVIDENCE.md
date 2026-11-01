# SENO execution evidence

All outputs below were produced by real command runs on 2026-11-01. The run started at 05:26:43 UTC on code commit `5e1a3c2d5ec2beb0195c1133a90e19279792cfce` (branch `feat/seno-portfolio-decision`, parent `46a2f0c`). Platform: macOS Darwin 25.6.0 arm64, Python 3.12.13, scipy 1.18.1, pandas 3.1.0, numpy 2.5.4, streamlit 1.66.1, scikit-learn 1.9.1, pytest 9.2.0.

**Every portfolio input is fictional (`SYNTHETIC`), a formula proxy (`PROXY`) or a planning assumption (`ASSUMPTION`). Every money and CO2 figure is a modeled estimate. Nothing below is a field result.**

## 1. Tests

```
.venv/bin/python -m pytest -v
============================== 64 passed in 4.62s ==============================
```

| File | Covers |
|---|---|
| `tests/test_schema.py` (18) | sample validates except deliberate FICT-11 error; lat/lon, GHI, emission factor, negative CAPEX, tariff cap, non-numeric; unit mismatch; mixed currency; zero tariff on grid site; measured without source/date; blank not labelled missing; duplicate towers within 25 m; duplicate rows; proxy label preserved |
| `tests/test_optimizer.py` (35) | budget exact fit; no feasible option (`all` vs `fixable` scope); budget too small for reliability → INFEASIBLE; zero-cost option at zero budget; identical scores deterministic + cheaper tie-break; multiple variants one-per-site and optimal; ineligible never chosen; high-case CAPEX basis; 25 random instances matched against brute force, with every plan within budget and one option per site; do_nothing; SciPy-missing fallback reports `HEURISTIC_FALLBACK` |
| `tests/test_options_and_workflow.py` (9) | four options per site; ineligible options have reasons and no numbers; savings/NPV/CO2 recomputed by hand from formula; evidence never upgraded; ranges bracket point values; full CLI workflow writes all artefacts; population never aggregated; legacy scoring still runs; forecast interface on synthetic panel + leakage guard |
| `tests/test_app_smoke.py` (2) | `app/streamlit_app.py` runs with no exception, shows the disclaimer, FICTIONAL banner, OPTIMAL status and SYNTHETIC labels; reports INFEASIBLE at a 20k budget |

The app was also opened in a browser at 1400×900. The browser console showed no errors and the server log no errors. Screenshots are in `docs/screenshots/`.

## 2. Complete example: input CSV → memo

```
.venv/bin/python scripts/seno_workflow.py --budget 60000 --max-diesel-hours 8 --out docs/example_run
```

Output (verbatim, trimmed to width):

```
Validated 10 sites; issues:
severity site_id          field                message
   error FICT-11 ghi_kwh_m2_day 12.5 above maximum 8.0
                    plan    status  sites_retrofitted    capex       npv  co2_avoided_t_yr  violations
              do_nothing  BASELINE                  0     0.00      0.00             0.000  reliability (<= 8 diesel h/day): ['FICT-01','FICT-02','FICT-04','FICT-09','FICT-10']
     legacy_score_greedy HEURISTIC                  2 41121.76 -28053.71            20.556  reliability ...: ['FICT-01','FICT-02','FICT-04','FICT-09','FICT-10']
     cost_benefit_greedy HEURISTIC                  2 23050.87   7616.58            20.739  reliability ...: ['FICT-01','FICT-04','FICT-09','FICT-10']
constrained_optimization   OPTIMAL                  5 59286.67  -2309.75            39.422  none
Optimizer: OPTIMAL | scipy.optimize.milp (HiGHS) scipy==1.18.1 | gap=0.0 | Optimization terminated successfully. (HiGHS Status 7: Optimal)
Chosen: FICT-01:pv_battery, FICT-02:pv_only, FICT-04:pv_only, FICT-09:pv_battery, FICT-10:pv_only
```

Artefacts in `docs/example_run/`: `validation_issues.csv`, `retrofit_options.csv`, `plan_comparison.csv`, `chosen_plan.csv`, `pareto_npv_co2.csv`, `decision_memo.md`, `decision_memo.html`.

The reliability constraint exempts FICT-06 (no PV space, no grid) and FICT-07 (no battery space) because none of their eligible options can reach 8 h/day. Both are listed as exceptions. The memo flags that the plan's high-case CAPEX (USD 83,001) exceeds the budget.

## 3. Before/after under identical inputs (fictional sample, 10 valid sites)

"Before" is the original method (`legacy_score_greedy`: balanced-weight min-max score, then prefix greedy on the full solar-hybrid option). "After" is the constrained MILP. Same options, same budget.

| Scenario | Plan | Sites | CAPEX (USD) | Modeled NPV (USD) | Modeled CO2 (t/yr) | Constraint violations |
|---|---|---:|---:|---:|---:|---|
| Budget 60k, maximise NPV | do_nothing | 0 | 0 | 0 | 0.0 | none |
| | legacy score + greedy | 2 | 41,122 | −28,054 | 20.6 | none |
| | cost/benefit greedy | 4 | 38,913 | 14,816 | 34.0 | none |
| | **MILP** | 4 | 38,913 | **14,816** | 34.0 | none |
| Budget 60k, maximise CO2 | legacy score + greedy | 2 | 41,122 | −28,054 | 20.6 | none |
| | cost/benefit greedy | 6 | 59,848 | 3,330 | 51.1 | none |
| | **MILP** | 6 | 59,880 | 9,733 | **51.9** | none |
| Budget 60k, ≤ 8 diesel h/day | legacy / cost-benefit greedy | 2 / 2 | 41,122 / 23,051 | −28,054 / 7,617 | 20.6 / 20.7 | 5 / 4 sites violate |
| | **MILP** | 5 | 59,287 | −2,310 | 39.4 | **none** |
| Budget 45k, ≤ 8 diesel h/day | **MILP** | – | – | – | – | **INFEASIBLE**, reported with a reason |
| Budget 60k, NPV, high-case CAPEX basis | MILP | 4 | 38,913 (high case fits) | 14,816 | 34.0 | none |

What this shows and does not show:
- The legacy method picks negative-NPV hybrids. Its prefix rule leaves USD 18.9k unused, and it never considers cheaper options.
- On this small instance the cost/benefit greedy **ties** the MILP for unconstrained NPV. The MILP adds value under the CO2 objective and, above all, under the reliability constraint, where only the MILP returns a plan that meets it. Randomised tests show the MILP always matches brute force. Greedy is not guaranteed to.
- Meeting reliability costs about USD 17k of NPV compared with the unconstrained optimum. That is an explicit trade-off for the planner, not a hidden weighting.
- NPV–CO2 Pareto sweep at 60k, no reliability cap (`pareto_npv_co2.csv` from the same CLI): (34.0 t, USD 14,816) → (39.9 t, 14,490) → (46.4 t, 13,616) → (51.9 t, 9,733).

## 4. Legacy reproduction (unchanged code)

Re-running `data_pipeline.process_tower_data` reproduces the committed `data/towers_enriched.csv` exactly (3,532 rows, max numeric diff 0.0). Details and the claim ledger are in `SENO_BASELINE_AUDIT.md`.

## 5. Acceptance criteria

| # | Criterion | Status |
|---|---|---|
| 1 | Existing app entry point still runs | TESTED (`streamlit run app/streamlit_app.py`; AppTest; browser) |
| 2 | 8–12 fictional towers complete the workflow | TESTED (11 towers, 1 rejected by validation, 10 optimised) |
| 3 | No plan exceeds CAPEX or assigns multiple options per site | TESTED (`check_plan` on every plan; 25 random instances) |
| 4 | do_nothing + two simple baselines on identical inputs | TESTED |
| 5 | Evidence types distinguishable in code, exports and visuals | TESTED (schema, CSV `evidence_label`, memo, UI text labels) |
| 6 | Savings traceable to formula, source, unit, assumptions | IMPLEMENTED; one option hand-recomputed in tests. Other options are covered by the same code path, not individually hand-checked |
| 7 | Predictive AI only if trained on suitable labels | Met by omission: ML is PLANNED and not advertised |
| 8 | Failures reported | No test failures in the final run. Earlier failures during development (one rounding tolerance) were fixed. Criterion 6 is partial as noted |

## 6. Not verified

- Data licences: primary licence pages were not opened (see `DATA_RIGHTS.md`).
- Behaviour on Python 3.9 (system Python), Windows or Linux.
- Any real-world accuracy of the energy model.
