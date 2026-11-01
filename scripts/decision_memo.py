"""
SUNTOWER-AI — portfolio decision memo (Markdown + printable one-page HTML) and CSV export.

The memo states the objective, constraints, solver status, plan comparison,
chosen investments with ranges and evidence labels, exclusions, assumptions
and the standing disclaimer. It never describes an estimate as a realised saving.
"""

from __future__ import annotations

import html
import os
import subprocess
from datetime import datetime, timezone
from typing import List, Optional

import pandas as pd

from site_schema import EVIDENCE_LABEL

DISCLAIMER = (
    "Decision-support output. All savings, emissions and reliability figures are modeled "
    "estimates from the inputs and assumptions listed; none is a measured or field-verified "
    "result. Inputs labelled SYNTHETIC are fictional and must not inform real investment."
)


def git_sha(short: bool = True) -> str:
    try:
        args = ["git", "rev-parse"] + (["--short"] if short else []) + ["HEAD"]
        return subprocess.run(args, capture_output=True, text=True, check=True,
                              cwd=os.path.dirname(os.path.abspath(__file__))).stdout.strip()
    except Exception:
        return "unknown"


def _money(v: float, cur: str) -> str:
    return f"{cur} {v:,.0f}"


def plan_export_frame(selection: pd.DataFrame) -> pd.DataFrame:
    """Reproducibility CSV: one row per site with chosen option, ranges and evidence labels."""
    cols = ["site_id", "site_name", "option", "pv_kwp", "battery_kwh", "capex", "capex_low", "capex_high",
            "annual_savings", "annual_savings_low", "annual_savings_high", "npv", "npv_low", "npv_high",
            "co2_avoided_t_yr", "diesel_l_avoided_yr", "grid_kwh_delta_yr", "baseline_diesel_h_day",
            "residual_diesel_h_day", "evidence_status", "diesel_basis", "currency", "formula"]
    out = selection[[c for c in cols if c in selection.columns]].copy()
    out.insert(out.columns.get_loc("evidence_status") + 1, "evidence_label",
               out["evidence_status"].map(EVIDENCE_LABEL))
    out["estimate_type"] = "modeled_estimate"
    return out


def build_memo_markdown(*, title: str, currency: str, budget: float, objective_label: str,
                        constraints: List[str], comparison: pd.DataFrame, chosen_plan: str,
                        selection: pd.DataFrame, solver_status: str, solver_message: str,
                        exclusions: pd.DataFrame, invalid_sites: pd.DataFrame,
                        assumptions: pd.DataFrame, evidence_counts: dict, data_label: str,
                        approved_by: Optional[str] = None) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    up = selection[selection["option"] != "do_nothing"]
    lines = [
        f"# {title}",
        "",
        f"*Generated {ts} · code {git_sha()} · data: {data_label}*",
        "",
        f"> {DISCLAIMER}",
        "",
        "## Decision",
        "",
        f"- Objective: maximise **{objective_label}** (single objective; no mixed-unit score)",
        f"- CAPEX budget: **{_money(budget, currency)}**; constraints: " + ("; ".join(constraints) or "budget only"),
        f"- Recommended plan: **{chosen_plan}** — solver status **{solver_status}** ({solver_message})",
        f"- Retrofits: **{len(up)}** of {len(selection)} valid sites; modeled CAPEX "
        f"{_money(up['capex'].sum(), currency)} (range {_money(up['capex_low'].sum(), currency)}"
        f"–{_money(up['capex_high'].sum(), currency)})",
        *([f"- **Cost risk:** at high-case CAPEX the plan costs {_money(up['capex_high'].sum(), currency)}, "
           f"above the budget; re-run with CAPEX basis = high for a plan that stays within budget."]
          if up["capex_high"].sum() > budget + 1e-6 else []),
        f"- Modeled NPV {_money(selection['npv'].sum(), currency)} (range {_money(selection['npv_low'].sum(), currency)}"
        f" to {_money(selection['npv_high'].sum(), currency)}); modeled CO2 avoided "
        f"{selection['co2_avoided_t_yr'].sum():,.1f} t/yr",
        "",
        "## Plans compared (identical inputs and budget)",
        "",
        "| Plan | Status | Sites | CAPEX | NPV | CO2 t/yr | Violations |",
        "|---|---|---:|---:|---:|---:|---|",
    ]
    for _, r in comparison.iterrows():
        lines.append(f"| {r['plan']} | {r['status']} | {r['sites_retrofitted']} | {r['capex']:,.0f} | "
                     f"{r['npv']:,.0f} | {r['co2_avoided_t_yr']:,.1f} | {r['violations']} |")
    lines += ["", "## Chosen investments", "",
              "| Site | Option | kWp | kWh | CAPEX (range) | NPV (range) | CO2 t/yr | Diesel h/day before→after | Evidence |",
              "|---|---|---:|---:|---|---|---:|---|---|"]
    for _, r in up.iterrows():
        lines.append(
            f"| {r['site_id']} | {r['option']} | {r['pv_kwp']:.1f} | {r['battery_kwh']:.1f} | "
            f"{r['capex']:,.0f} ({r['capex_low']:,.0f}–{r['capex_high']:,.0f}) | "
            f"{r['npv']:,.0f} ({r['npv_low']:,.0f}–{r['npv_high']:,.0f}) | {r['co2_avoided_t_yr']:.1f} | "
            f"{r['baseline_diesel_h_day']:.1f}→{r['residual_diesel_h_day']:.1f} | {EVIDENCE_LABEL[r['evidence_status']]} |")
    if up.empty:
        lines.append("| — | no retrofit selected | | | | | | | |")
    lines += ["", "## Exclusions", ""]
    if len(invalid_sites):
        for _, r in invalid_sites.iterrows():
            lines.append(f"- Site **{r['site_id']}** excluded by validation: {r['field']} — {r['message']}")
    for _, r in exclusions.iterrows():
        lines.append(f"- {r['site_id']} · {r['option']}: {r['exclusion_reason']}")
    if not len(invalid_sites) and exclusions.empty:
        lines.append("- none")
    lines += ["", "## Evidence behind inputs", "",
              ", ".join(f"{EVIDENCE_LABEL[k]}: {v}" for k, v in evidence_counts.items() if v) or "n/a",
              "", "## Assumptions", ""]
    for _, r in assumptions.iterrows():
        lines.append(f"- {r['assumption']} = {r['value']} {r['unit']} — {r['rationale']}")
    lines += ["", "## Approval", "",
              f"- Reviewed and approved by: {approved_by or '________________'}   Date: ____________",
              "- Before any field decision: replace SYNTHETIC/ASSUMPTION inputs with operator or measured data, "
              "obtain vendor quotes, and re-run.", ""]
    return "\n".join(lines)


def memo_html(markdown_text: str) -> str:
    """Minimal Markdown→HTML for the memo's own subset (headings, lists, tables, quotes), print-ready."""
    out, in_table, in_list = [], False, False
    for raw in markdown_text.splitlines():
        line = raw.rstrip()
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if set("".join(cells)) <= set("-:"):
                continue
            if not in_table:
                out.append("<table>")
                tag, in_table = "th", True
            else:
                tag = "td"
            out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
            continue
        if in_table:
            out.append("</table>")
            in_table = False
        if line.startswith("- "):
            if not in_list:
                out.append("<ul>")
                in_list = True
            out.append(f"<li>{_inline(line[2:])}</li>")
            continue
        if in_list:
            out.append("</ul>")
            in_list = False
        if line.startswith("# "):
            out.append(f"<h1>{_inline(line[2:])}</h1>")
        elif line.startswith("## "):
            out.append(f"<h2>{_inline(line[3:])}</h2>")
        elif line.startswith("> "):
            out.append(f"<p class='note'>{_inline(line[2:])}</p>")
        elif line:
            out.append(f"<p>{_inline(line)}</p>")
    if in_table:
        out.append("</table>")
    if in_list:
        out.append("</ul>")
    css = ("body{font:10.5px/1.35 Georgia,serif;color:#111;max-width:190mm;margin:10mm auto}"
           "h1{font-size:17px;margin:0 0 2px}h2{font-size:12px;margin:10px 0 3px;border-bottom:1px solid #999;"
           "text-transform:uppercase;letter-spacing:.04em}table{border-collapse:collapse;width:100%;font:9.5px/1.3 "
           "Helvetica,Arial,sans-serif}th,td{border-bottom:1px solid #ddd;padding:2px 4px;text-align:left}"
           "th{border-bottom:1px solid #333}.note{border-left:3px solid #333;padding:3px 7px;background:#f3f3f3}"
           "ul{margin:2px 0 2px 16px;padding:0}@page{size:A4;margin:10mm}")
    return f"<!doctype html><html><head><meta charset='utf-8'><title>Portfolio memo</title><style>{css}</style>" \
           f"</head><body>{''.join(out)}</body></html>"


def _inline(text: str) -> str:
    t = html.escape(text)
    while "**" in t:
        t = t.replace("**", "<b>", 1).replace("**", "</b>", 1)
    if t.startswith("*") and t.endswith("*") and len(t) > 2:
        t = f"<i>{t[1:-1]}</i>"
    return t
