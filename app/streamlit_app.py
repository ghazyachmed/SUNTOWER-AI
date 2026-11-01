"""
SUNTOWER-AI — retrofit portfolio decision support (Streamlit).

User path: set budget → inspect evidence → compare plans → examine exclusions → approve/export.
The legacy 3,532-row screening map is kept as its own tab, relabelled as formula-based proxies.

ASEAN GeoAI Fusion 2026 Hackathon — Team HACK-ID-068 (extended for SENO Hackathon ITS 2026)
"""

import os
import sys

import folium
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from streamlit_folium import st_folium

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from scoring_engine import (  # noqa: E402
    compute_scores, budget_allocation, compute_impact, SCENARIO_WEIGHTS,
)
from retrofit_options import ASSUMPTIONS, assumptions_frame, with_overrides  # noqa: E402
from portfolio_optimizer import OBJECTIVES  # noqa: E402
from seno_workflow import SAMPLE_PATH, run_workflow  # noqa: E402
from site_schema import EVIDENCE_LABEL, evidence_matrix, load_portfolio_csv  # noqa: E402

st.set_page_config(page_title="SUNTOWER-AI · Retrofit portfolio", page_icon="☀️", layout="wide")

# Editorial styling: type hierarchy and rules, no gradients or glow.
st.markdown("""
<style>
  .block-container {padding-top: 1.4rem; max-width: 1280px;}
  h1 {font-weight: 700; letter-spacing: -0.01em; margin-bottom: 0;}
  h2, h3 {font-weight: 650; border-bottom: 1px solid rgba(128,128,128,.35); padding-bottom: .2rem;}
  .kicker {text-transform: uppercase; letter-spacing: .08em; font-size: .72rem; opacity: .7; margin: 0;}
  .stat {font-variant-numeric: tabular-nums;}
  .stat b {font-size: 1.35rem; display: block; line-height: 1.2;}
  .stat span {font-size: .75rem; opacity: .75;}
</style>
""", unsafe_allow_html=True)

DISCLAIMER = ("**Decision support, not proof of field savings.** Every saving, emission and reliability figure "
              "on this page is a modeled estimate from the listed inputs and assumptions. The map and scenarios "
              "do not show measured outcomes.")


def stat(col, value, label):
    col.markdown(f"<div class='stat'><b>{value}</b><span>{label}</span></div>", unsafe_allow_html=True)


def money(v, cur):
    return f"{cur} {v:,.0f}"


@st.cache_data(show_spinner=False)
def cached_workflow(records, budget, objective, max_diesel_hours, scope, capex_basis, overrides,
                    data_label, approved_by):
    return run_workflow(records, budget, objective, max_diesel_hours, scope, capex_basis,
                        with_overrides(**dict(overrides)), data_label, approved_by=approved_by)


# -------------------------------------------------------------------
# 1 · Budget and constraints (sidebar)
# -------------------------------------------------------------------
def render_sidebar():
    with st.sidebar:
        st.markdown("### 1 · Budget and constraints")
        source = st.radio("Portfolio data", ["Fictional sample (11 towers)", "Upload long-format CSV"])
        records, label = None, None
        if source.startswith("Fictional"):
            records, label = load_portfolio_csv(SAMPLE_PATH), "sample_portfolio_fictional.csv (FICTIONAL)"
        else:
            up = st.file_uploader("CSV: site_id, field, value, unit, source, as_of_date, evidence_type, "
                                  "uncertainty_pct, notes", type="csv")
            if up is not None:
                records, label = load_portfolio_csv(up), up.name
        budget = st.number_input("CAPEX budget", min_value=0, value=60_000, step=5_000,
                                 help="Total retrofit CAPEX across the portfolio, in the portfolio currency")
        objective = st.radio("Objective (one quantity, no blended score)", list(OBJECTIVES),
                             format_func=lambda k: f"Maximise {OBJECTIVES[k][1]}")
        use_rel = st.checkbox("Reliability constraint", value=True,
                              help="Cap estimated residual generator hours per day at each site")
        max_h, scope = None, "fixable"
        if use_rel:
            max_h = float(st.slider("Max residual diesel hours/day", 0, 24, 8))
            scope = st.radio("Applies to", ["fixable", "all"],
                             format_func=lambda s: {"fixable": "Sites where an option can meet it",
                                                    "all": "Every site (hard)"}[s])
        capex_basis = st.radio("CAPEX basis for the budget", ["point", "high"],
                               format_func=lambda s: {"point": "Point estimate",
                                                      "high": "High case (cost overrun)"}[s])
        with st.expander("Analysis assumptions"):
            dr = st.number_input("Discount rate", 0.0, 0.5, ASSUMPTIONS["discount_rate"].value, 0.01)
            hz = st.number_input("Horizon (years)", 1, 30, int(ASSUMPTIONS["horizon_years"].value))
            pr = st.number_input("PV performance ratio", 0.5, 0.95, ASSUMPTIONS["pv_performance_ratio"].value, 0.01)
            au = st.number_input("Battery autonomy (h)", 1.0, 24.0, ASSUMPTIONS["battery_autonomy_h"].value, 0.5)
        overrides = (("discount_rate", dr), ("horizon_years", hz), ("pv_performance_ratio", pr),
                     ("battery_autonomy_h", au))
        st.caption("ASEAN GeoAI Fusion 2026 · HACK-ID-068")
    return records, label, float(budget), objective, max_h, scope, capex_basis, overrides


# -------------------------------------------------------------------
# 2 · Evidence
# -------------------------------------------------------------------
def render_evidence(res):
    st.markdown("Every input carries an evidence label. Labels are text, so they survive printing and "
                "do not depend on colour.")
    counts = res["evidence_counts"]
    cols = st.columns(len(EVIDENCE_LABEL))
    for col, (k, lab) in zip(cols, EVIDENCE_LABEL.items()):
        stat(col, counts.get(k, 0), lab)
    issues = res["issues"]
    st.markdown("#### Validation")
    if issues.empty:
        st.write("No validation issues.")
    else:
        st.dataframe(issues, hide_index=True, width="stretch")
    st.markdown("#### Evidence matrix (valid sites)")
    st.dataframe(evidence_matrix(res["sites"]), hide_index=True, width="stretch")
    st.markdown("#### Field detail")
    sid = st.selectbox("Site", [s.site_id for s in res["sites"]], key="ev_site")
    site = next(s for s in res["sites"] if s.site_id == sid)
    rows = [{"field": f, "value": fv.value, "unit": fv.unit, "evidence": EVIDENCE_LABEL[fv.evidence_type],
             "uncertainty ±%": fv.uncertainty_pct, "as of": fv.as_of_date, "source": fv.source, "notes": fv.notes}
            for f, fv in site.fields.items()]
    st.dataframe(pd.DataFrame(rows).astype({"value": str}), hide_index=True, width="stretch")


# -------------------------------------------------------------------
# 3 · Compare plans
# -------------------------------------------------------------------
def render_compare(res, budget, objective):
    cur = res["currency"]
    opt = res["optimal"]
    status_line = f"Optimizer status: **{opt.status}** · {opt.solver} · MIP gap {opt.mip_gap} · {opt.message}"
    (st.success if opt.status == "OPTIMAL" else st.error)(status_line)
    st.markdown("**Constraints:** " + "; ".join(res["constraints"]))
    if res["reliability_exceptions"]:
        st.warning("Reliability exceptions (no eligible option can meet the target): "
                   + ", ".join(res["reliability_exceptions"]))
    comp = res["comparison"].copy()
    show = comp[["plan", "status", "sites_retrofitted", "capex", "capex_high", "npv", "npv_low", "npv_high",
                 "co2_avoided_t_yr", "diesel_l_avoided_yr", "max_residual_diesel_h_day", "weakest_evidence",
                 "violations", "active_constraints"]]
    st.dataframe(show, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%.0f") for c in
        ["capex", "capex_high", "npv", "npv_low", "npv_high", "diesel_l_avoided_yr"]})
    st.caption(f"All four plans use identical inputs, options and budget ({money(budget, cur)}). "
               "do_nothing and the two greedy rules are baselines; only the MILP is checked for optimality.")

    left, right = st.columns(2)
    with left:
        fig = go.Figure(go.Bar(
            y=comp["plan"], x=comp["npv"], orientation="h", marker_color="#4a6fa5",
            error_x=dict(type="data", symmetric=False, array=comp["npv_high"] - comp["npv"],
                         arrayminus=comp["npv"] - comp["npv_low"]),
            text=[f"{v:,.0f}" for v in comp["npv"]], textposition="outside"))
        fig.update_layout(title=f"Modeled NPV with input-uncertainty range ({cur})", height=300,
                          margin=dict(t=40, b=20, l=10, r=40), yaxis=dict(autorange="reversed"))
        st.plotly_chart(fig, width="stretch")
    with right:
        par = res.get("pareto")
        if par is not None and len(par) == 1:
            st.markdown("**NPV vs CO2 trade-off:** only one non-dominated plan exists under the current "
                        "constraints, so there is no trade-off to show.")
        elif par is not None and len(par):
            fig2 = go.Figure(go.Scatter(x=par["co2_avoided_t_yr"], y=par["npv"], mode="lines+markers+text",
                                        text=[f"{c:,.0f}" for c in par["capex"]], textposition="top center",
                                        line=dict(color="#555")))
            fig2.update_layout(title="NPV vs CO2 trade-off (labels: CAPEX)", xaxis_title="tCO2/yr avoided",
                               yaxis_title=f"NPV ({cur})", height=300, margin=dict(t=40, b=40, l=10, r=10))
            st.plotly_chart(fig2, width="stretch")
            st.caption("Epsilon-constraint sweep: max NPV subject to CO2 ≥ ε. Dollars and tonnes are never summed.")

    st.markdown("#### Option chosen per site, by plan")
    mat = pd.DataFrame({name: p.selection.set_index("site_id")["option"] for name, p in res["plans"].items()})
    st.dataframe(mat, width="stretch")


# -------------------------------------------------------------------
# 4 · Sites and exclusions
# -------------------------------------------------------------------
def render_sites(res, objective):
    sel = res["optimal"].selection
    t = sel[["site_id", "option", "pv_kwp", "battery_kwh", "capex_low", "capex", "capex_high", "npv_low", "npv",
             "npv_high", "co2_avoided_t_yr", "baseline_diesel_h_day", "residual_diesel_h_day",
             "evidence_status"]].copy()
    t["evidence"] = t.pop("evidence_status").map(EVIDENCE_LABEL)
    st.markdown("#### Recommended plan, site by site")
    st.dataframe(t, hide_index=True, width="stretch", column_config={
        c: st.column_config.NumberColumn(format="%.0f") for c in
        ["capex_low", "capex", "capex_high", "npv_low", "npv", "npv_high"]})

    st.markdown("#### Why this option?")
    sid = st.selectbox("Site", list(sel["site_id"]), key="rat_site")
    opts = res["options"][res["options"]["site_id"] == sid].copy()
    picked = sel.set_index("site_id").loc[sid, "option"]
    obj_col = OBJECTIVES[objective][0]
    st.write(f"**{sid}** → **{picked}**. The optimizer picks the combination of one option per site that "
             f"maximises total {OBJECTIVES[objective][1]} within the budget and constraints, so a site can get a "
             "cheaper option than its individual best when funds are better used elsewhere.")
    opts["evidence"] = opts["evidence_status"].map(EVIDENCE_LABEL)
    st.dataframe(opts[["option", "eligible", "exclusion_reason", "capex", obj_col, "annual_savings",
                       "residual_diesel_h_day", "evidence", "formula"]], hide_index=True, width="stretch")

    st.markdown("#### Exclusions")
    inv = res["invalid_sites"]
    if len(inv):
        st.markdown("Sites rejected by validation (not optimized):")
        st.dataframe(inv, hide_index=True, width="stretch")
    st.markdown("Options not available at a site:")
    st.dataframe(res["exclusions"], hide_index=True, width="stretch")


# -------------------------------------------------------------------
# 5 · Approve and export
# -------------------------------------------------------------------
def render_export(res):
    st.markdown("Review the memo, confirm you checked evidence labels and exclusions, then export.")
    st.markdown(res["memo_md"])
    ok = st.checkbox("I reviewed the evidence labels, exclusions and cost ranges")
    c1, c2, c3, c4 = st.columns(4)
    c1.download_button("Memo (printable HTML)", res["memo_html"], "suntower_portfolio_memo.html", "text/html",
                       disabled=not ok)
    c2.download_button("Memo (Markdown)", res["memo_md"], "suntower_portfolio_memo.md", "text/markdown",
                       disabled=not ok)
    c3.download_button("Chosen plan (CSV)", res["plan_csv"].to_csv(index=False), "suntower_chosen_plan.csv",
                       "text/csv", disabled=not ok)
    c4.download_button("All options (CSV)", res["options"].to_csv(index=False), "suntower_options.csv",
                       "text/csv", disabled=not ok)
    st.markdown("#### Assumptions used")
    st.dataframe(assumptions_frame(), hide_index=True, width="stretch")


# -------------------------------------------------------------------
# Legacy screening map (original v2 data, relabelled)
# -------------------------------------------------------------------
@st.cache_data
def load_legacy():
    path = os.path.join(os.path.dirname(__file__), '..', 'data', 'towers_enriched.csv')
    if not os.path.exists(path):
        return None
    return pd.read_csv(path)


def get_color(score):
    if score >= 7.5:
        return '#1b7f3b'
    if score >= 5.0:
        return '#b8860b'
    if score >= 2.5:
        return '#c0582b'
    return '#6b7280'


def render_legacy():
    st.markdown(
        "Original SUNTOWER v2 screening of 3,532 rows from the Bandung tower list. **Every attribute below "
        "is produced by formulas in `scripts/data_pipeline.py`** (GHI, elevation, population, night lights, "
        "grid status, road distance, energy, cost) — none is a satellite observation or site measurement. "
        "See `docs/SENO_BASELINE_AUDIT.md`.")
    st.markdown("- The source lists the same inventory for 2017–2020, so many towers appear up to four times.\n"
                "- 3,531 of 3,532 rows are classified 'Strong Grid' by the night-light proxy.\n"
                "- 5-km population proxies overlap, so their sum is **not** people served.")
    df = load_legacy()
    if df is None:
        st.info("Run `python scripts/data_pipeline.py` to create data/towers_enriched.csv.")
        return
    c1, c2 = st.columns(2)
    budget = c1.slider("Legacy budget (USD)", 100_000, 10_000_000, 2_000_000, 100_000, key="lg_budget")
    scenario = c2.selectbox("Legacy weights", list(SCENARIO_WEIGHTS), key="lg_scen")
    scored = compute_scores(df, SCENARIO_WEIGHTS[scenario])
    selected = budget_allocation(scored, budget, candidates_only=False)
    imp = compute_impact(selected)
    cols = st.columns(4)
    stat(cols[0], imp['towers_selected'], "rows selected (score + prefix greedy)")
    stat(cols[1], f"${imp['annual_savings_usd']:,.0f}", "modeled savings/yr (proxy inputs)")
    stat(cols[2], f"{imp['annual_co2_avoided_tonnes']:,.0f} t", "modeled CO2/yr (proxy inputs)")
    stat(cols[3], f"{imp['population_served']:,.0f}", "sum of overlapping 5-km proxies — NOT people served")
    if st.checkbox("Draw map (3,532 markers, slow)", key="lg_map"):
        sel_ids = set(selected['id'])
        m = folium.Map(location=[scored['lat'].mean(), scored['long'].mean()], zoom_start=11,
                       tiles="cartodbpositron", control_scale=True)
        for _, r in scored.iterrows():
            chosen = r['id'] in sel_ids
            folium.CircleMarker(
                [r['lat'], r['long']], radius=5 if chosen else 2.5, color=get_color(r['suntower_score_10']),
                fill=True, fill_opacity=0.85 if chosen else 0.3, weight=1,
                tooltip=(f"Row {int(r['id'])} · score {r['suntower_score_10']:.1f} (proxy) · "
                         f"{'selected' if chosen else 'not selected'}")).add_to(m)
        st_folium(m, height=480, use_container_width=True, returned_objects=[])
        st.caption("Marker size = selected by legacy greedy; colour = legacy score band. Decision-support only.")
    if len(selected):
        st.download_button("Legacy priority list (CSV)", selected.to_csv(index=False),
                           "suntower_priority_list.csv", "text/csv")


# -------------------------------------------------------------------
# Main
# -------------------------------------------------------------------
def main():
    records, label, budget, objective, max_h, scope, capex_basis, overrides = render_sidebar()
    st.markdown("<p class='kicker'>SUNTOWER-AI · Telecom TowerCo energy planning</p>", unsafe_allow_html=True)
    st.title("Retrofit portfolio decision")
    st.info(DISCLAIMER)

    res = None
    if records is not None:
        if "FICTIONAL" in (label or ""):
            st.warning("Data: **FICTIONAL sample portfolio.** Sites, coordinates and values are invented for "
                       "demonstration and do not describe real towers.")
        approver = st.session_state.get("approver") or None
        res = cached_workflow(records, budget, objective, max_h, scope, capex_basis, overrides, label, approver)
        if "error" not in res:
            cur = res["currency"]
            sel = res["optimal"].selection
            up = sel[sel["option"] != "do_nothing"]
            cols = st.columns(5)
            stat(cols[0], f"{len(up)} / {len(sel)}", "sites retrofitted (valid sites)")
            stat(cols[1], money(up['capex'].sum(), cur), f"CAPEX of {money(budget, cur)} budget")
            stat(cols[2], money(sel['npv'].sum(), cur), f"modeled NPV ({money(sel['npv_low'].sum(), cur)} to "
                                                        f"{money(sel['npv_high'].sum(), cur)})")
            stat(cols[3], f"{sel['co2_avoided_t_yr'].sum():,.1f} t", "modeled CO2 avoided per year")
            stat(cols[4], res["optimal"].status, "optimizer status")

    tabs = st.tabs(["2 · Evidence", "3 · Compare plans", "4 · Sites & exclusions", "5 · Approve & export",
                    "Legacy screening map"])
    with tabs[4]:
        render_legacy()
    if res is None:
        for t in tabs[:4]:
            t.info("Upload a portfolio CSV in the sidebar (see data/sample_portfolio_fictional.csv for the format).")
        return
    if "error" in res:
        for t in tabs[:4]:
            t.error(res["error"])
        tabs[0].dataframe(res["issues"], hide_index=True)
        return
    with tabs[0]:
        render_evidence(res)
    with tabs[1]:
        render_compare(res, budget, objective)
    with tabs[2]:
        render_sites(res, objective)
    with tabs[3]:
        st.text_input("Approver name (printed on memo)", key="approver")
        render_export(res)


if __name__ == "__main__":
    main()
