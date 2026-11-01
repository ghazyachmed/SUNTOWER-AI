import os

import pandas as pd
import pytest

from energy_forecast import LABEL_CONTRACT, evaluate, make_synthetic_panel
from retrofit_options import ASSUMPTIONS, annuity_factor, build_option_table
from scoring_engine import budget_allocation, compute_scores
from seno_workflow import SAMPLE_PATH, main, run_workflow
from site_schema import load_portfolio_csv, validate_portfolio

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


@pytest.fixture(scope="module")
def sample():
    recs = load_portfolio_csv(SAMPLE_PATH)
    sites, _ = validate_portfolio(recs)
    return recs, sites, build_option_table(sites)


def test_four_options_per_site_and_do_nothing_is_zero(sample):
    _, sites, opts = sample
    assert len(opts) == 4 * len(sites)
    dn = opts[opts.option == "do_nothing"]
    assert (dn[["capex", "npv", "co2_avoided_t_yr"]] == 0).all().all()


def test_ineligible_options_have_reasons_and_no_numbers(sample):
    _, _, opts = sample
    inel = opts[~opts.eligible]
    assert len(inel) > 0 and (inel.exclusion_reason.str.len() > 0).all()
    assert inel.capex.isna().all() and inel.npv.isna().all()
    reasons = dict(zip(inel.site_id + ":" + inel.option, inel.exclusion_reason))
    assert "grid" in reasons["FICT-01:battery_only"].lower()
    assert "pv space" in reasons["FICT-06:pv_only"].lower()


def test_savings_formula_is_traceable(sample):
    _, sites, opts = sample
    s = next(x for x in sites if x.site_id == "FICT-01")      # off-grid: all PV offsets diesel
    r = opts[(opts.site_id == "FICT-01") & (opts.option == "pv_only")].iloc[0]
    pr, genset = ASSUMPTIONS["pv_performance_ratio"].value, ASSUMPTIONS["genset_kwh_per_l"].value
    day_load = s.get("load_kw_avg") * 24 * ASSUMPTIONS["default_daytime_load_fraction"].value
    kwp = min(s.get("max_pv_kwp"), day_load / (s.get("ghi_kwh_m2_day") * pr))   # unrounded sizing rule
    used = min(kwp * s.get("ghi_kwh_m2_day") * pr, day_load)
    assert r.pv_kwp == pytest.approx(kwp, abs=0.005)
    capex = s.get("fixed_install_capex") + kwp * s.get("pv_capex_per_kwp")
    savings = 365 * used / genset * s.get("diesel_price_per_l") - capex * ASSUMPTIONS["om_pct_capex"].value
    assert r.capex == pytest.approx(capex, abs=0.05)
    assert r.annual_savings == pytest.approx(savings, abs=0.05)
    af = annuity_factor(ASSUMPTIONS["discount_rate"].value, ASSUMPTIONS["horizon_years"].value)
    assert r.npv == pytest.approx(-r.capex + r.annual_savings * af, abs=0.1)
    assert r.co2_avoided_t_yr == pytest.approx(365 * used / genset * 2.68 / 1000, abs=1e-3)


def test_evidence_status_never_upgraded(sample):
    _, _, opts = sample
    up = opts[opts.eligible & (opts.option != "do_nothing")]
    assert set(up.evidence_status) == {"synthetic"}  # fictional inputs stay synthetic end to end


def test_ranges_bracket_point_estimates(sample):
    _, _, opts = sample
    up = opts[opts.eligible & (opts.option != "do_nothing")]
    assert (up.capex_low <= up.capex).all() and (up.capex <= up.capex_high).all()
    assert (up.npv_low <= up.npv + 1e-6).all() and (up.npv <= up.npv_high + 1e-6).all()


def test_full_workflow_fictional_portfolio(tmp_path):
    rc = main(["--budget", "60000", "--max-diesel-hours", "8", "--out", str(tmp_path)])
    assert rc == 0
    for f in ["validation_issues.csv", "retrofit_options.csv", "plan_comparison.csv", "chosen_plan.csv",
              "decision_memo.md", "decision_memo.html", "pareto_npv_co2.csv"]:
        assert (tmp_path / f).exists()
    comp = pd.read_csv(tmp_path / "plan_comparison.csv")
    assert list(comp.plan) == ["do_nothing", "legacy_score_greedy", "cost_benefit_greedy",
                               "constrained_optimization"]
    assert (comp.capex <= 60000 + 1e-6).all()
    plan = pd.read_csv(tmp_path / "chosen_plan.csv")
    assert plan.site_id.is_unique and set(plan.estimate_type) == {"modeled_estimate"}
    assert set(plan.evidence_label) == {"SYNTHETIC"}
    memo = (tmp_path / "decision_memo.md").read_text()
    assert "not a measured" in memo.lower() or "none is a measured" in memo.lower()
    assert "FICT-11" in memo  # validation exclusion surfaced


def test_population_proxy_never_aggregated():
    res = run_workflow(load_portfolio_csv(SAMPLE_PATH), 60000, pareto_points=0)
    assert not any("population" in c for c in res["comparison"].columns)
    assert "population" not in res["memo_md"].lower()


def test_legacy_scoring_engine_still_works():
    df = pd.read_csv(os.path.join(ROOT, "data", "towers_enriched.csv"))
    scored = compute_scores(df)
    sel = budget_allocation(scored, 500_000, candidates_only=False)
    assert sel.capex_usd.sum() <= 500_000 and len(sel) > 0


def test_forecast_interface_on_synthetic_panel_only():
    df = make_synthetic_panel()
    assert set(df.evidence_type) == {"synthetic"}
    rep = evaluate(df, cutoff="2025-07-01", holdout_sites=["SYN-00", "SYN-01", "SYN-02"],
                   data_label="SYNTHETIC unit-test panel")
    assert rep.n_sites_test == 3 and rep.train_end < rep.test_start
    assert rep.mae_baseline > 0 and rep.mae_model is not None
    with pytest.raises(ValueError):
        evaluate(df, "2025-07-01", ["SYN-00"], "x", features=list(LABEL_CONTRACT["forbidden"]))
