"""
SUNTOWER-AI — end-to-end portfolio workflow (shared by the CLI and the Streamlit app).

input CSV → validation → modeled option estimates → four-plan comparison →
chosen investments → memo + reproducibility CSV.

    python scripts/seno_workflow.py --budget 60000 --max-diesel-hours 8 --out outputs/example
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from typing import Optional

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from decision_memo import build_memo_markdown, memo_html, plan_export_frame  # noqa: E402
from portfolio_optimizer import (OBJECTIVES, compare_plans, pareto_frontier,  # noqa: E402
                                 reliability_exceptions)
from retrofit_options import ASSUMPTIONS, assumptions_frame, build_option_table  # noqa: E402
from site_schema import (issues_frame, load_portfolio_csv, sites_to_wide,  # noqa: E402
                         validate_portfolio)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SAMPLE_PATH = os.path.join(ROOT, "data", "sample_portfolio_fictional.csv")


def run_workflow(records: pd.DataFrame, budget: float, objective: str = "npv",
                 max_diesel_hours: Optional[float] = None, reliability_scope: str = "fixable",
                 capex_basis: str = "point", assumptions=ASSUMPTIONS, data_label: str = "uploaded",
                 pareto_points: int = 8, approved_by: Optional[str] = None) -> dict:
    sites, issues = validate_portfolio(records)
    issues_df = issues_frame(issues)
    all_ids = list(dict.fromkeys(records["site_id"].astype(str).str.strip()))
    invalid_ids = [s for s in all_ids if s not in {x.site_id for x in sites}]
    invalid_df = issues_df[(issues_df["severity"] == "error")
                           & issues_df["site_id"].isin(invalid_ids + ["*"])]
    result = {"sites": sites, "issues": issues_df, "invalid_sites": invalid_df, "records": records}
    if not sites:
        result["error"] = "No valid sites after validation."
        return result

    options = build_option_table(sites, assumptions)
    wide = sites_to_wide(sites)
    comparison, plans = compare_plans(options, budget, wide, objective, max_diesel_hours,
                                      capex_basis, reliability_scope)
    opt = plans["constrained_optimization"]
    currency = str(wide["currency"].iloc[0])
    constraints = [f"one option per site; total {'high-case ' if capex_basis == 'high' else ''}CAPEX <= budget"]
    if max_diesel_hours is not None:
        constraints.append(f"residual diesel <= {max_diesel_hours:g} h/day per site ({reliability_scope} scope)")
    exceptions = reliability_exceptions(options, max_diesel_hours)
    evidence_counts = Counter(r["evidence_type"] for _, r in records.iterrows()
                              if str(r["site_id"]).strip() not in invalid_ids)
    exclusions = options[~options["eligible"].astype(bool)][["site_id", "option", "exclusion_reason"]]
    memo_md = build_memo_markdown(
        title="SUNTOWER-AI retrofit portfolio memo", currency=currency, budget=budget,
        objective_label=OBJECTIVES[objective][1], constraints=constraints, comparison=comparison,
        chosen_plan="constrained_optimization", selection=opt.selection, solver_status=opt.status,
        solver_message=f"{opt.solver}; {opt.message}".strip("; "), exclusions=exclusions,
        invalid_sites=invalid_df, assumptions=assumptions_frame(assumptions),
        evidence_counts=dict(evidence_counts), data_label=data_label, approved_by=approved_by)
    result.update({
        "options": options, "wide": wide, "comparison": comparison, "plans": plans,
        "optimal": opt, "currency": currency, "constraints": constraints,
        "reliability_exceptions": exceptions, "exclusions": exclusions,
        "evidence_counts": dict(evidence_counts), "memo_md": memo_md, "memo_html": memo_html(memo_md),
        "plan_csv": plan_export_frame(opt.selection),
        "pareto": pareto_frontier(options, budget, pareto_points, max_diesel_hours, capex_basis,
                                  reliability_scope) if pareto_points else None,
    })
    return result


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", default=SAMPLE_PATH, help="Long-format portfolio CSV")
    ap.add_argument("--budget", type=float, required=True)
    ap.add_argument("--objective", choices=list(OBJECTIVES), default="npv")
    ap.add_argument("--max-diesel-hours", type=float, default=None)
    ap.add_argument("--reliability-scope", choices=["fixable", "all"], default="fixable")
    ap.add_argument("--capex-basis", choices=["point", "high"], default="point")
    ap.add_argument("--out", default=os.path.join(ROOT, "outputs", "example"))
    args = ap.parse_args(argv)

    records = load_portfolio_csv(args.input)
    res = run_workflow(records, args.budget, args.objective, args.max_diesel_hours,
                       args.reliability_scope, args.capex_basis, data_label=os.path.basename(args.input))
    os.makedirs(args.out, exist_ok=True)
    res["issues"].to_csv(os.path.join(args.out, "validation_issues.csv"), index=False)
    print(f"Validated {len(res['sites'])} sites; issues:\n{res['issues'].to_string(index=False)}")
    if "error" in res:
        print(res["error"])
        return 1
    res["options"].to_csv(os.path.join(args.out, "retrofit_options.csv"), index=False)
    res["comparison"].to_csv(os.path.join(args.out, "plan_comparison.csv"), index=False)
    res["plan_csv"].to_csv(os.path.join(args.out, "chosen_plan.csv"), index=False)
    if res["pareto"] is not None:
        res["pareto"].to_csv(os.path.join(args.out, "pareto_npv_co2.csv"), index=False)
    with open(os.path.join(args.out, "decision_memo.md"), "w") as f:
        f.write(res["memo_md"])
    with open(os.path.join(args.out, "decision_memo.html"), "w") as f:
        f.write(res["memo_html"])
    cols = ["plan", "status", "sites_retrofitted", "capex", "npv", "co2_avoided_t_yr", "violations"]
    with pd.option_context("display.width", 200, "display.max_colwidth", 60):
        print(res["comparison"][cols].to_string(index=False))
    o = res["optimal"]
    print(f"Optimizer: {o.status} | {o.solver} | gap={o.mip_gap} | {o.message}")
    print("Chosen:", ", ".join(f"{r.site_id}:{r.option}" for r in o.selection.itertuples() if r.option != "do_nothing")
          or "none")
    print(f"Outputs written to {os.path.abspath(args.out)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
