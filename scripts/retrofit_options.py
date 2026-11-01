"""
SUNTOWER-AI — retrofit option generation (modeled estimates, not field results).

For each validated site this module builds do_nothing, pv_only, battery_only and
pv_battery options where the inputs permit, with CAPEX, annual savings, NPV,
CO2 change, residual diesel dependence, uncertainty ranges and the weakest
evidence type behind each estimate. Every number is a formula of the site
inputs and the ASSUMPTIONS below; nothing here is a measured saving.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import pandas as pd

from site_schema import EVIDENCE_RANK, SiteFeatures


@dataclass(frozen=True)
class Assumption:
    value: float
    unit: str
    rationale: str


# Engineering/finance assumptions. Values are planning defaults, not measurements.
ASSUMPTIONS: Dict[str, Assumption] = {
    "pv_performance_ratio": Assumption(0.75, "fraction",
                                       "Typical PR for small off-grid/hybrid PV incl. temperature and wiring losses"),
    "battery_round_trip_eff": Assumption(0.90, "fraction", "Lithium-ion round-trip efficiency"),
    "battery_depth_of_discharge": Assumption(0.80, "fraction", "Usable share of nominal capacity"),
    "battery_autonomy_h": Assumption(4.0, "h", "Target storage autonomy at average load"),
    "genset_kwh_per_l": Assumption(3.0, "kWh/L", "Same constant as legacy data_pipeline.py"),
    "default_daytime_load_fraction": Assumption(0.5, "fraction", "Flat telecom load over ~12 sun hours"),
    "discount_rate": Assumption(0.10, "1/yr", "Planning discount rate; replace with operator WACC"),
    "horizon_years": Assumption(10, "yr", "Analysis horizon; battery replacement not modeled"),
    "om_pct_capex": Assumption(0.02, "1/yr", "Annual O&M as share of retrofit CAPEX"),
}

OPTIONS = ("do_nothing", "pv_only", "battery_only", "pv_battery")

FORMULAS = {
    "baseline": "E=load_kw*24; diesel_kWh = diesel_L*genset_kWh_per_L if reported else E*(24-grid_h)/24; "
                "grid_kWh = E - diesel_kWh",
    "pv_only": "kWp=min(max_pv, E*day_frac/(GHI*PR)); used=min(kWp*GHI*PR, E*day_frac); "
               "diesel share of used = diesel_kWh/E",
    "battery_only": "kWh_nom=min(max_batt, load*autonomy/DoD); shifted=min(kWh_nom*DoD, diesel_kWh); "
                    "grid charging = shifted/RTE",
    "pv_battery": "kWp=min(max_pv, E/(GHI*PR)); direct=min(Y, E*day_frac); "
                  "stored=min((Y-direct)*RTE, kWh_nom*DoD, E*(1-day_frac)); stored offsets diesel first",
    "economics": "savings=365*(diesel_L_off*price + grid_kWh_off*tariff) - O&M; "
                 "NPV=-CAPEX + savings*annuity(r, N); CO2=365*(diesel_L_off*EF_d + grid_kWh_off*EF_g)/1000",
}


def annuity_factor(rate: float, years: float) -> float:
    if rate == 0:
        return float(years)
    return (1 - (1 + rate) ** -years) / rate


def _weakest(site: SiteFeatures, names: List[str]) -> str:
    evs = [site.evidence(n) for n in names]
    return max(evs, key=lambda e: EVIDENCE_RANK[e]) if evs else "assumption"


def _rss(*pcts: float) -> float:
    return math.sqrt(sum(p * p for p in pcts))


def site_baseline(site: SiteFeatures, a: Dict[str, Assumption] = ASSUMPTIONS) -> dict:
    load = float(site.get("load_kw_avg"))
    grid_h = float(site.get("grid_hours_per_day"))
    e_day = load * 24
    diesel_l = site.get("diesel_l_per_day")
    if diesel_l is not None:
        diesel_kwh = min(e_day, float(diesel_l) * a["genset_kwh_per_l"].value)
        diesel_basis = site.evidence("diesel_l_per_day")
    else:
        diesel_kwh = e_day * (24 - grid_h) / 24
        diesel_l = diesel_kwh / a["genset_kwh_per_l"].value
        diesel_basis = "modeled_proxy"
    grid_kwh = max(0.0, e_day - diesel_kwh)
    return {
        "e_day_kwh": e_day,
        "diesel_kwh_day": diesel_kwh,
        "diesel_l_day": float(diesel_l),
        "diesel_basis": diesel_basis,
        "grid_kwh_day": grid_kwh,
        "diesel_hours_day": diesel_kwh / load if load > 0 else 0.0,
    }


def _option_row(site, name, base, *, kwp=0.0, kwh=0.0, diesel_kwh_off=0.0, grid_kwh_off=0.0,
                inputs=(), eligible=True, reason="", a=ASSUMPTIONS) -> dict:
    cur = site.get("currency")
    price = float(site.get("diesel_price_per_l"))
    tariff = float(site.get("grid_tariff_per_kwh") or 0.0)
    ef_d = float(site.get("diesel_ef_kg_per_l"))
    ef_g = float(site.get("grid_ef_kg_per_kwh"))
    genset = a["genset_kwh_per_l"].value
    fixed = float(site.get("fixed_install_capex", 0.0) or 0.0)

    capex = 0.0
    if name != "do_nothing":
        capex = fixed + kwp * float(site.get("pv_capex_per_kwp")) + kwh * float(site.get("battery_capex_per_kwh"))
    diesel_l_off = diesel_kwh_off / genset
    om = capex * a["om_pct_capex"].value
    savings = 365 * (diesel_l_off * price + grid_kwh_off * tariff) - om
    co2 = 365 * (diesel_l_off * ef_d + grid_kwh_off * ef_g) / 1000
    af = annuity_factor(a["discount_rate"].value, a["horizon_years"].value)
    npv = -capex + savings * af

    # Uncertainty: CAPEX from cost-field uncertainty; savings from the main yield/price drivers.
    cost_fields = [f for f, used in (("pv_capex_per_kwp", kwp > 0), ("battery_capex_per_kwh", kwh > 0),
                                     ("fixed_install_capex", name != "do_nothing")) if used]
    capex_u = max([site.uncertainty(f) for f in cost_fields] or [0.0]) / 100
    drivers = ["load_kw_avg", "diesel_price_per_l", "grid_tariff_per_kwh"] + (["ghi_kwh_m2_day"] if kwp > 0 else [])
    sav_u = _rss(*[site.uncertainty(f) for f in drivers]) / 100
    gross = savings + om
    sav_low, sav_high = gross * (1 - sav_u) - om * (1 + capex_u), gross * (1 + sav_u) - om * (1 - capex_u)
    capex_low, capex_high = capex * (1 - capex_u), capex * (1 + capex_u)

    residual_diesel_kwh = max(0.0, base["diesel_kwh_day"] - diesel_kwh_off)
    load = float(site.get("load_kw_avg"))
    used_fields = list(inputs) + ["load_kw_avg", "grid_hours_per_day", "diesel_price_per_l",
                                  "diesel_ef_kg_per_l", "grid_ef_kg_per_kwh"]
    if site.get("diesel_l_per_day") is not None:
        used_fields.append("diesel_l_per_day")
    weakest = _weakest(site, used_fields)
    if base["diesel_basis"] == "modeled_proxy" and EVIDENCE_RANK[weakest] < EVIDENCE_RANK["modeled_proxy"]:
        weakest = "modeled_proxy"

    row = {
        "site_id": site.site_id,
        "site_name": site.get("site_name"),
        "option": name,
        "eligible": eligible,
        "exclusion_reason": reason,
        "currency": cur,
        "pv_kwp": round(kwp, 2),
        "battery_kwh": round(kwh, 2),
        "capex": round(capex, 2),
        "capex_low": round(capex_low, 2),
        "capex_high": round(capex_high, 2),
        "annual_savings": round(savings, 2),
        "annual_savings_low": round(sav_low, 2),
        "annual_savings_high": round(sav_high, 2),
        "npv": round(npv, 2),
        "npv_low": round(-capex_high + sav_low * af, 2),
        "npv_high": round(-capex_low + sav_high * af, 2),
        "co2_avoided_t_yr": round(co2, 3),
        "diesel_l_avoided_yr": round(365 * diesel_l_off, 1),
        "grid_kwh_delta_yr": round(-365 * grid_kwh_off, 1),
        "baseline_diesel_h_day": round(base["diesel_hours_day"], 2),
        "residual_diesel_h_day": round(residual_diesel_kwh / load if load > 0 else 0.0, 2),
        "evidence_status": weakest,
        "diesel_basis": base["diesel_basis"],
        "formula": FORMULAS.get(name, "no change"),
    }
    if not eligible:
        # Not applicable: blank the estimates so exclusions never display misleading numbers.
        for k in ("pv_kwp", "battery_kwh", "capex", "capex_low", "capex_high", "annual_savings",
                  "annual_savings_low", "annual_savings_high", "npv", "npv_low", "npv_high",
                  "co2_avoided_t_yr", "diesel_l_avoided_yr", "grid_kwh_delta_yr", "residual_diesel_h_day"):
            row[k] = float("nan")
        row["formula"] = ""
    return row


def build_options(site: SiteFeatures, a: Dict[str, Assumption] = ASSUMPTIONS) -> List[dict]:
    """All four options for a site; ineligible ones are kept with a reason (for the exclusions view)."""
    base = site_baseline(site, a)
    load = float(site.get("load_kw_avg"))
    e_day = base["e_day_kwh"]
    grid_h = float(site.get("grid_hours_per_day"))
    ghi = site.get("ghi_kwh_m2_day")
    pr = a["pv_performance_ratio"].value
    rte = a["battery_round_trip_eff"].value
    dod = a["battery_depth_of_discharge"].value
    day_frac = float(site.get("daytime_load_fraction", a["default_daytime_load_fraction"].value))
    max_pv = float(site.get("max_pv_kwp") or 0.0)
    max_batt = float(site.get("max_battery_kwh") or 0.0)
    diesel_share = base["diesel_kwh_day"] / e_day if e_day > 0 else 0.0
    pv_in = ["ghi_kwh_m2_day", "pv_capex_per_kwp", "max_pv_kwp"]
    batt_in = ["battery_capex_per_kwh", "max_battery_kwh"]

    rows = [_option_row(site, "do_nothing", base, a=a)]

    # pv_only
    if ghi is None or max_pv <= 0:
        rows.append(_option_row(site, "pv_only", base, eligible=False, a=a,
                                reason="No PV space (max_pv_kwp=0)" if max_pv <= 0 else "GHI missing"))
    else:
        kwp = min(max_pv, e_day * day_frac / (ghi * pr))
        used = min(kwp * ghi * pr, e_day * day_frac)
        rows.append(_option_row(site, "pv_only", base, kwp=kwp, diesel_kwh_off=used * diesel_share,
                                grid_kwh_off=used * (1 - diesel_share), inputs=pv_in, a=a))

    # battery_only: grid-charged storage that replaces generator hours.
    if max_batt <= 0:
        rows.append(_option_row(site, "battery_only", base, eligible=False, a=a,
                                reason="No battery space (max_battery_kwh=0)"))
    elif grid_h <= 0:
        rows.append(_option_row(site, "battery_only", base, eligible=False, a=a,
                                reason="No grid to charge from (grid_hours_per_day=0)"))
    elif base["diesel_kwh_day"] <= 0:
        rows.append(_option_row(site, "battery_only", base, eligible=False, a=a,
                                reason="No diesel use to displace"))
    else:
        kwh = min(max_batt, load * a["battery_autonomy_h"].value / dod)
        # Charging energy must fit in grid hours on top of the load (assumes connection headroom = 1x load).
        charge_cap = load * grid_h
        shifted = min(kwh * dod, base["diesel_kwh_day"], charge_cap * rte)
        rows.append(_option_row(site, "battery_only", base, kwh=kwh, diesel_kwh_off=shifted,
                                grid_kwh_off=-shifted / rte, inputs=batt_in, a=a))

    # pv_battery
    if ghi is None or max_pv <= 0 or max_batt <= 0:
        why = "No PV space" if max_pv <= 0 else ("GHI missing" if ghi is None else "No battery space")
        rows.append(_option_row(site, "pv_battery", base, eligible=False, a=a, reason=why))
    else:
        kwp = min(max_pv, e_day / (ghi * pr))
        kwh = min(max_batt, load * a["battery_autonomy_h"].value / dod)
        y = kwp * ghi * pr
        direct = min(y, e_day * day_frac)
        stored = min((y - direct) * rte, kwh * dod, e_day * (1 - day_frac))
        diesel_off_direct = direct * diesel_share
        diesel_off = min(base["diesel_kwh_day"], diesel_off_direct + stored)
        grid_off = max(0.0, direct + stored - diesel_off)
        rows.append(_option_row(site, "pv_battery", base, kwp=kwp, kwh=kwh, diesel_kwh_off=diesel_off,
                                grid_kwh_off=grid_off, inputs=pv_in + batt_in, a=a))
    return rows


def build_option_table(sites: List[SiteFeatures], a: Dict[str, Assumption] = ASSUMPTIONS) -> pd.DataFrame:
    rows = []
    for s in sites:
        rows.extend(build_options(s, a))
    return pd.DataFrame(rows)


def assumptions_frame(a: Dict[str, Assumption] = ASSUMPTIONS) -> pd.DataFrame:
    return pd.DataFrame([{"assumption": k, "value": v.value, "unit": v.unit, "evidence_type": "assumption",
                          "rationale": v.rationale} for k, v in a.items()])


def with_overrides(**overrides: float) -> Dict[str, Assumption]:
    out = dict(ASSUMPTIONS)
    for k, v in overrides.items():
        if v is None:
            continue
        old = out[k]
        out[k] = Assumption(v, old.unit, old.rationale + " (user override)")
    return out

