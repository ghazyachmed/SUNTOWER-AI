"""
SUNTOWER-AI — constrained multi-site retrofit selection and baselines.

Problem (multiple-choice knapsack, solved as a MILP with SciPy/HiGHS):

    maximise   sum_i sum_k  obj[i,k] * x[i,k]
    subject to sum_k x[i,k] = 1                 for every site i  (one option, do_nothing allowed)
               sum_{i,k} capex[i,k] * x[i,k] <= budget
               x[i,k] = 0 if option ineligible, or if it leaves residual diesel
                          hours/day above max_diesel_hours (optional reliability constraint)
               sum co2[i,k] x[i,k] >= min_co2   (optional epsilon constraint, Pareto sweep)
               x binary

obj is ONE explicit quantity: 'npv' (currency) or 'co2' (tCO2/yr). Dollars and
tonnes are never added together; trade-offs are shown with pareto_frontier().

If SciPy's milp is unavailable the cost/benefit greedy heuristic is used and the
status says HEURISTIC_FALLBACK (no optimality claim).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from site_schema import EVIDENCE_RANK  # noqa: E402

try:
    import scipy
    from scipy.optimize import LinearConstraint, Bounds, milp
    SOLVER_NAME = f"scipy.optimize.milp (HiGHS) scipy=={scipy.__version__}"
except ImportError:  # pragma: no cover - exercised only when scipy is absent
    milp = None
    SOLVER_NAME = "unavailable"

OBJECTIVES = {"npv": ("npv", "NPV"), "co2": ("co2_avoided_t_yr", "tCO2/yr avoided")}
CAPEX_BASIS = {"point": "capex", "high": "capex_high"}


@dataclass
class PlanResult:
    name: str
    selection: pd.DataFrame            # one row per site: the chosen option
    status: str                        # OPTIMAL | INFEASIBLE | HEURISTIC | HEURISTIC_FALLBACK | BASELINE
    solver: str = ""
    message: str = ""
    mip_gap: Optional[float] = None
    notes: List[str] = field(default_factory=list)


def reliability_exceptions(options: pd.DataFrame, max_diesel_hours: Optional[float]) -> List[str]:
    """Sites where no eligible option (including do_nothing) can meet the diesel-hours target."""
    if max_diesel_hours is None:
        return []
    meets = options["eligible"].astype(bool) & (options["residual_diesel_h_day"] <= max_diesel_hours + 1e-9)
    ok_sites = set(options.loc[meets, "site_id"])
    return [s for s in dict.fromkeys(options["site_id"]) if s not in ok_sites]


def _allowed(options: pd.DataFrame, max_diesel_hours: Optional[float],
             reliability_scope: str = "fixable") -> pd.Series:
    """
    Eligible options that satisfy the reliability constraint.
    scope='all'     : every site must meet max_diesel_hours (infeasible if any site cannot).
    scope='fixable' : sites with no option able to meet it are exempted and reported as exceptions.
    """
    ok = options["eligible"].astype(bool)
    if max_diesel_hours is not None:
        meets = options["residual_diesel_h_day"] <= max_diesel_hours + 1e-9
        if reliability_scope == "fixable":
            meets |= options["site_id"].isin(reliability_exceptions(options, max_diesel_hours))
        ok &= meets
    return ok


def _assemble(options: pd.DataFrame, chosen: dict) -> pd.DataFrame:
    """chosen: site_id -> option name. Sites not in chosen get do_nothing."""
    rows = []
    for sid, grp in options.groupby("site_id", sort=False):
        opt = chosen.get(sid, "do_nothing")
        rows.append(grp[grp["option"] == opt].iloc[0])
    return pd.DataFrame(rows).reset_index(drop=True)


def optimize_portfolio(options: pd.DataFrame, budget: float, objective: str = "npv",
                       max_diesel_hours: Optional[float] = None, min_co2: Optional[float] = None,
                       capex_basis: str = "point", reliability_scope: str = "fixable",
                       time_limit_s: float = 30.0) -> PlanResult:
    obj_col = OBJECTIVES[objective][0]
    cap_col = CAPEX_BASIS[capex_basis]
    if milp is None:
        res = plan_cost_benefit_greedy(options, budget, objective, max_diesel_hours, capex_basis,
                                       reliability_scope)
        res.name, res.status = "constrained_optimization", "HEURISTIC_FALLBACK"
        res.message = "SciPy milp unavailable; greedy heuristic used, optimality not guaranteed"
        return res

    cand = options[_allowed(options, max_diesel_hours, reliability_scope)].reset_index(drop=True)
    sites = list(dict.fromkeys(options["site_id"]))
    missing = [s for s in sites if s not in set(cand["site_id"])]
    if missing:
        return PlanResult("constrained_optimization", _assemble(options, {}), "INFEASIBLE", SOLVER_NAME,
                          f"No option satisfies the reliability constraint at sites: {missing}")

    n = len(cand)
    obj = cand[obj_col].to_numpy(float)
    capex = cand[cap_col].to_numpy(float)
    # Deterministic tie-break toward lower CAPEX; magnitude far below any reported precision.
    scale = max(1.0, np.abs(obj).max())
    c = -(obj - 1e-7 * scale * capex / max(1.0, capex.max()))

    a_site = np.zeros((len(sites), n))
    idx = {s: k for k, s in enumerate(sites)}
    for j, sid in enumerate(cand["site_id"]):
        a_site[idx[sid], j] = 1.0
    cons = [LinearConstraint(a_site, 1, 1), LinearConstraint(capex[None, :], -np.inf, budget)]
    if min_co2 is not None:
        cons.append(LinearConstraint(cand["co2_avoided_t_yr"].to_numpy(float)[None, :], min_co2, np.inf))

    res = milp(c, constraints=cons, integrality=np.ones(n), bounds=Bounds(0, 1),
               options={"time_limit": time_limit_s, "mip_rel_gap": 1e-9})
    gap = getattr(res, "mip_gap", None)
    if res.status != 0 or res.x is None:
        status = "INFEASIBLE" if res.status == 2 else f"SOLVER_STATUS_{res.status}"
        msg = res.message
        if res.status == 2 and max_diesel_hours is not None:
            msg = "Budget too small to bring every constrained site to the diesel-hours target. " + msg
        return PlanResult("constrained_optimization", _assemble(options, {}), status, SOLVER_NAME, msg, gap)
    pick = cand[res.x > 0.5]
    chosen = dict(zip(pick["site_id"], pick["option"]))
    return PlanResult("constrained_optimization", _assemble(options, chosen), "OPTIMAL", SOLVER_NAME,
                      res.message, gap)


def plan_do_nothing(options: pd.DataFrame) -> PlanResult:
    return PlanResult("do_nothing", _assemble(options, {}), "BASELINE", "none", "No retrofit at any site")


def plan_cost_benefit_greedy(options: pd.DataFrame, budget: float, objective: str = "npv",
                             max_diesel_hours: Optional[float] = None, capex_basis: str = "point",
                             reliability_scope: str = "fixable") -> PlanResult:
    """Rank upgrade options by objective per unit CAPEX; take the best that still fits, one per site."""
    obj_col = OBJECTIVES[objective][0]
    cap_col = CAPEX_BASIS[capex_basis]
    up = options[_allowed(options, max_diesel_hours, reliability_scope) & (options["option"] != "do_nothing")].copy()
    up = up[up[obj_col] > 0]
    up["ratio"] = np.where(up[cap_col] > 0, up[obj_col] / up[cap_col].where(up[cap_col] > 0, 1), np.inf)
    up = up.sort_values(["ratio", obj_col, "site_id", "option"], ascending=[False, False, True, True])
    remaining, chosen = float(budget), {}
    for _, r in up.iterrows():
        if r["site_id"] in chosen or r[cap_col] > remaining + 1e-9:
            continue
        chosen[r["site_id"]] = r["option"]
        remaining -= r[cap_col]
    return PlanResult("cost_benefit_greedy", _assemble(options, chosen), "HEURISTIC", "greedy",
                      f"Ranked by {OBJECTIVES[objective][1]} per unit CAPEX")


def plan_legacy_score_greedy(options: pd.DataFrame, budget: float, sites_wide: pd.DataFrame,
                             capex_basis: str = "point") -> PlanResult:
    """
    Reproduces the original SUNTOWER approach: min-max weighted 'balanced' score
    (scoring_engine.compute_scores) and prefix-cumsum greedy (budget_allocation)
    applied to each site's full solar-hybrid (pv_battery) retrofit.
    """
    from scoring_engine import SCENARIO_WEIGHTS, budget_allocation, compute_scores

    cap_col = CAPEX_BASIS[capex_basis]
    hyb = options[(options["option"] == "pv_battery") & options["eligible"]].merge(
        sites_wide[["site_id", "ghi_kwh_m2_day", "service_population_proxy", "road_distance_km"]],
        on="site_id", how="left")
    notes = ["Legacy method only considers the pv_battery retrofit; sites where it is ineligible are skipped."]
    if hyb.empty:
        return PlanResult("legacy_score_greedy", _assemble(options, {}), "HEURISTIC", "legacy", "", notes=notes)
    pop = hyb["service_population_proxy"].fillna(0)
    frame = pd.DataFrame({
        "id": hyb["site_id"],
        "ghi_kwh_m2_day": hyb["ghi_kwh_m2_day"],
        "total_savings_usd_year": hyb["annual_savings"],
        "co2_avoided_tonnes_year": hyb["co2_avoided_t_yr"],
        # Legacy equity = population x nightlight gap; nightlight is not in the schema, so population only.
        "connectivity_equity": pop / pop.max() if pop.max() > 0 else 0.0,
        "road_distance_km": hyb["road_distance_km"].fillna(hyb["road_distance_km"].median()),
        "capex_usd": hyb[cap_col],
        "is_off_grid": 1,
    })
    notes.append("Equity term uses the population proxy only (no nightlight field in the schema).")
    scored = compute_scores(frame, SCENARIO_WEIGHTS["balanced"])
    picked = budget_allocation(scored, budget, candidates_only=False)
    chosen = {sid: "pv_battery" for sid in picked["id"]}
    return PlanResult("legacy_score_greedy", _assemble(options, chosen), "HEURISTIC", "legacy",
                      "Balanced-weight score, prefix greedy (stops at first tower that does not fit)", notes=notes)


def check_plan(plan: PlanResult, options: pd.DataFrame, budget: float,
               max_diesel_hours: Optional[float] = None, capex_basis: str = "point",
               reliability_scope: str = "fixable") -> dict:
    """Post-hoc audit of any plan: budget, one-option-per-site, eligibility, reliability."""
    sel = plan.selection
    cap_col = CAPEX_BASIS[capex_basis]
    spend = float(sel[cap_col].sum())
    violated, active = [], []
    if spend > budget + 1e-6:
        violated.append(f"budget: spend {spend:,.0f} > {budget:,.0f}")
    if sel["site_id"].duplicated().any():
        violated.append("one-option-per-site: duplicate site assignments")
    if set(sel["site_id"]) != set(options["site_id"]):
        violated.append("coverage: not every site has a decision")
    if (~sel["eligible"].astype(bool)).any():
        violated.append("eligibility: ineligible option selected")
    if max_diesel_hours is not None:
        exempt = reliability_exceptions(options, max_diesel_hours) if reliability_scope == "fixable" else []
        bad = sel[(sel["residual_diesel_h_day"] > max_diesel_hours + 1e-9)
                  & ~sel["site_id"].isin(exempt)]["site_id"].tolist()
        if bad:
            violated.append(f"reliability (<= {max_diesel_hours:g} diesel h/day): {bad}")
        else:
            active.append(f"reliability (<= {max_diesel_hours:g} diesel h/day) met"
                          + (f"; exempt (no eligible option can meet it): {exempt}" if exempt else ""))
    # Budget is active when no remaining eligible upgrade (that is an improvement) still fits.
    left = budget - spend
    chosen = dict(zip(sel["site_id"], sel["option"]))
    alt = options[options["eligible"].astype(bool) & (options["option"] != "do_nothing")]
    alt = alt[alt["site_id"].map(chosen).eq("do_nothing")]
    if not violated and len(alt) and (alt[cap_col] > left + 1e-9).all():
        active.append(f"budget binding: {left:,.0f} left, cheapest unfunded upgrade {alt[cap_col].min():,.0f}")
    elif not violated and len(alt):
        active.append(f"budget not binding: {int((alt[cap_col] <= left + 1e-9).sum())} affordable upgrades "
                      f"left unfunded because they do not improve the objective")
    return {"violated": violated, "active": active, "budget_left": left}


def evaluate_plan(plan: PlanResult, options: pd.DataFrame, budget: float,
                  max_diesel_hours: Optional[float] = None, capex_basis: str = "point",
                  reliability_scope: str = "fixable") -> dict:
    sel = plan.selection
    chk = check_plan(plan, options, budget, max_diesel_hours, capex_basis, reliability_scope)
    upgraded = sel[sel["option"] != "do_nothing"]
    return {
        "plan": plan.name,
        "status": plan.status,
        "sites_retrofitted": int(len(upgraded)),
        "capex": float(sel["capex"].sum()),
        "capex_high": float(sel["capex_high"].sum()),
        "budget_left": chk["budget_left"],
        "annual_savings": float(sel["annual_savings"].sum()),
        "npv": float(sel["npv"].sum()),
        "npv_low": float(sel["npv_low"].sum()),
        "npv_high": float(sel["npv_high"].sum()),
        "co2_avoided_t_yr": float(sel["co2_avoided_t_yr"].sum()),
        "diesel_l_avoided_yr": float(sel["diesel_l_avoided_yr"].sum()),
        "max_residual_diesel_h_day": float(sel["residual_diesel_h_day"].max()),
        "weakest_evidence": (max(upgraded["evidence_status"], key=EVIDENCE_RANK.get)
                             if len(upgraded) else "n/a"),
        "violations": "; ".join(chk["violated"]) or "none",
        "active_constraints": "; ".join(chk["active"]) or "none",
    }


def compare_plans(options: pd.DataFrame, budget: float, sites_wide: pd.DataFrame, objective: str = "npv",
                  max_diesel_hours: Optional[float] = None, capex_basis: str = "point",
                  reliability_scope: str = "fixable"):
    """Run the four plans on identical inputs. Returns (comparison DataFrame, {name: PlanResult})."""
    plans = [
        plan_do_nothing(options),
        plan_legacy_score_greedy(options, budget, sites_wide, capex_basis),
        plan_cost_benefit_greedy(options, budget, objective, max_diesel_hours, capex_basis, reliability_scope),
        optimize_portfolio(options, budget, objective, max_diesel_hours, capex_basis=capex_basis,
                           reliability_scope=reliability_scope),
    ]
    rows = [evaluate_plan(p, options, budget, max_diesel_hours, capex_basis, reliability_scope) for p in plans]
    return pd.DataFrame(rows), {p.name: p for p in plans}


def pareto_frontier(options: pd.DataFrame, budget: float, n_points: int = 8,
                    max_diesel_hours: Optional[float] = None, capex_basis: str = "point",
                    reliability_scope: str = "fixable") -> pd.DataFrame:
    """epsilon-constraint sweep: max NPV subject to CO2 >= eps, eps from 0 to the CO2 maximum."""
    best_co2 = optimize_portfolio(options, budget, "co2", max_diesel_hours, capex_basis=capex_basis,
                                  reliability_scope=reliability_scope)
    if best_co2.status != "OPTIMAL":
        return pd.DataFrame(columns=["min_co2", "npv", "co2_avoided_t_yr", "capex", "status"])
    co2_max = float(best_co2.selection["co2_avoided_t_yr"].sum())
    rows = []
    for eps in np.linspace(0, co2_max, n_points):
        p = optimize_portfolio(options, budget, "npv", max_diesel_hours, min_co2=float(eps) - 1e-6,
                               capex_basis=capex_basis, reliability_scope=reliability_scope)
        rows.append({"min_co2": float(eps), "npv": float(p.selection["npv"].sum()),
                     "co2_avoided_t_yr": float(p.selection["co2_avoided_t_yr"].sum()),
                     "capex": float(p.selection["capex"].sum()), "status": p.status})
    return pd.DataFrame(rows).drop_duplicates(["npv", "co2_avoided_t_yr"])
