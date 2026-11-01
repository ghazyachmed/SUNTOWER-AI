import itertools

import numpy as np
import pandas as pd
import pytest

from portfolio_optimizer import (check_plan, compare_plans, optimize_portfolio, plan_cost_benefit_greedy,
                                 plan_do_nothing, reliability_exceptions)


def opt_row(site, option, capex=0.0, npv=0.0, co2=0.0, resid=0.0, eligible=True, capex_u=0.0):
    return {"site_id": site, "site_name": site, "option": option, "eligible": eligible, "exclusion_reason": "",
            "currency": "USD", "pv_kwp": 0.0, "battery_kwh": 0.0, "capex": capex,
            "capex_low": capex * (1 - capex_u), "capex_high": capex * (1 + capex_u),
            "annual_savings": npv / 6, "annual_savings_low": npv / 6, "annual_savings_high": npv / 6,
            "npv": npv, "npv_low": npv, "npv_high": npv, "co2_avoided_t_yr": co2, "diesel_l_avoided_yr": 0.0,
            "grid_kwh_delta_yr": 0.0, "baseline_diesel_h_day": 24.0, "residual_diesel_h_day": resid,
            "evidence_status": "synthetic", "diesel_basis": "synthetic", "formula": ""}


def frame(rows):
    return pd.DataFrame([opt_row(*r) if isinstance(r, tuple) else opt_row(**r) for r in rows])


def chosen(plan):
    return {r.site_id: r.option for r in plan.selection.itertuples() if r.option != "do_nothing"}


def brute_force(options, budget, col="npv"):
    best = 0.0
    groups = [g for _, g in options[options.eligible].groupby("site_id")]
    for combo in itertools.product(*[list(g.itertuples()) for g in groups]):
        if sum(c.capex for c in combo) <= budget + 1e-9:
            best = max(best, sum(getattr(c, col) for c in combo))
    return best


def test_budget_exact_fit():
    o = frame([("A", "do_nothing"), ("A", "pv_only", 100, 30),
               ("B", "do_nothing"), ("B", "pv_only", 50, 20)])
    p = optimize_portfolio(o, 150)
    assert p.status == "OPTIMAL" and chosen(p) == {"A": "pv_only", "B": "pv_only"}
    assert p.selection.capex.sum() == pytest.approx(150)
    assert check_plan(p, o, 150)["violated"] == []


def test_no_feasible_option_under_reliability_all_scope():
    o = frame([("A", "do_nothing", 0, 0, 0, 24), ("A", "pv_only", 10, 5, 1, 12)])
    p = optimize_portfolio(o, 1000, max_diesel_hours=4, reliability_scope="all")
    assert p.status == "INFEASIBLE" and chosen(p) == {}
    assert reliability_exceptions(o, 4) == ["A"]
    # fixable scope exempts A and optimizes normally
    p2 = optimize_portfolio(o, 1000, max_diesel_hours=4, reliability_scope="fixable")
    assert p2.status == "OPTIMAL" and chosen(p2) == {"A": "pv_only"}


def test_budget_too_small_for_reliability_is_infeasible():
    o = frame([("A", "do_nothing", 0, 0, 0, 24), ("A", "pv_battery", 500, -10, 5, 2)])
    p = optimize_portfolio(o, 100, max_diesel_hours=4)
    assert p.status == "INFEASIBLE"
    p2 = optimize_portfolio(o, 500, max_diesel_hours=4)
    assert p2.status == "OPTIMAL" and chosen(p2) == {"A": "pv_battery"}  # forced despite negative NPV


def test_zero_cost_option_selected_with_zero_budget():
    o = frame([("A", "do_nothing"), ("A", "tariff_switch", 0, 40), ("B", "do_nothing"), ("B", "pv_only", 10, 50)])
    p = optimize_portfolio(o, 0)
    assert chosen(p) == {"A": "tariff_switch"}
    g = plan_cost_benefit_greedy(o, 0)
    assert chosen(g) == {"A": "tariff_switch"}


def test_identical_scores_deterministic_and_within_budget():
    o = frame([("A", "do_nothing"), ("A", "pv_only", 100, 30), ("B", "do_nothing"), ("B", "pv_only", 100, 30)])
    picks = {tuple(sorted(chosen(optimize_portfolio(o, 150)).items())) for _ in range(5)}
    assert len(picks) == 1 and len(next(iter(picks))) == 1
    # tie in objective -> cheaper option preferred
    o2 = frame([("A", "do_nothing"), ("A", "pv_only", 100, 30), ("A", "pv_battery", 120, 30)])
    assert chosen(optimize_portfolio(o2, 500)) == {"A": "pv_only"}


def test_multiple_variants_one_per_site_and_optimal():
    o = frame([("A", "do_nothing"), ("A", "pv_only", 60, 20), ("A", "battery_only", 40, 5),
               ("A", "pv_battery", 100, 35), ("B", "do_nothing"), ("B", "pv_only", 50, 18),
               ("B", "pv_battery", 90, 25)])
    p = optimize_portfolio(o, 150)
    assert p.selection.site_id.is_unique
    assert p.selection.npv.sum() == pytest.approx(brute_force(o, 150))


def test_ineligible_options_never_selected():
    o = frame([("A", "do_nothing"), dict(site="A", option="pv_only", capex=1, npv=1000, eligible=False)])
    assert chosen(optimize_portfolio(o, 100)) == {}


def test_uncertain_costs_high_basis_respects_budget_in_high_case():
    o = frame([dict(site=s, option="do_nothing") for s in "ABCD"] +
              [dict(site=s, option="pv_only", capex=100, npv=50, capex_u=0.5) for s in "ABCD"])
    point = optimize_portfolio(o, 400)
    high = optimize_portfolio(o, 400, capex_basis="high")
    assert point.selection.capex.sum() <= 400 and point.selection.capex_high.sum() > 400
    assert high.selection.capex_high.sum() <= 400


@pytest.mark.parametrize("seed", range(25))
def test_random_instances_match_brute_force_and_baselines_respect_budget(seed):
    rng = np.random.default_rng(seed)
    rows = []
    for s in range(int(rng.integers(2, 6))):
        rows.append(dict(site=f"S{s}", option="do_nothing", resid=24))
        for k in ["pv_only", "battery_only", "pv_battery"]:
            c = float(rng.integers(1, 40)) * 500
            rows.append(dict(site=f"S{s}", option=k, capex=c, npv=float(rng.normal(0, 8000)),
                             co2=float(rng.uniform(0, 10)), resid=float(rng.uniform(0, 20)),
                             eligible=bool(rng.random() > 0.2)))
    o = frame(rows)
    budget = float(rng.integers(0, 60)) * 500
    p = optimize_portfolio(o, budget)
    assert p.status == "OPTIMAL"
    assert p.selection.npv.sum() == pytest.approx(brute_force(o, budget), abs=1e-6)
    wide = pd.DataFrame({"site_id": o.site_id.unique(), "ghi_kwh_m2_day": 5.0,
                         "service_population_proxy": 1000.0, "road_distance_km": 1.0})
    comp, plans = compare_plans(o, budget, wide)
    for plan in plans.values():
        assert plan.selection.site_id.is_unique
        assert plan.selection.capex.sum() <= budget + 1e-6
    assert comp.set_index("plan").loc["constrained_optimization", "npv"] >= comp.npv.max() - 1e-6


def test_do_nothing_baseline():
    o = frame([("A", "do_nothing"), ("A", "pv_only", 10, 5)])
    p = plan_do_nothing(o)
    assert chosen(p) == {} and p.selection.capex.sum() == 0


def test_fallback_without_scipy_reports_heuristic(monkeypatch):
    import portfolio_optimizer as po
    monkeypatch.setattr(po, "milp", None)
    o = frame([("A", "do_nothing"), ("A", "pv_only", 100, 30), ("B", "do_nothing"), ("B", "pv_only", 50, 20)])
    p = po.optimize_portfolio(o, 120)
    assert p.status == "HEURISTIC_FALLBACK" and "not guaranteed" in p.message
    assert p.selection.capex.sum() <= 120
