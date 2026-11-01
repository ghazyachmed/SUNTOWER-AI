"""
SUNTOWER-AI — typed site_features schema, data dictionary and validation.

Every site attribute is carried as a FieldValue with value, unit, source,
as_of_date, evidence_type and (optionally) a symmetric uncertainty in percent.
Portfolio inputs are long-format CSV files with one row per (site_id, field):

    site_id,field,value,unit,source,as_of_date,evidence_type,uncertainty_pct,notes

The validator never converts a modeled proxy into an observation: evidence
labels travel unchanged from input to options, plans, exports and the UI.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd


EVIDENCE_TYPES = (
    "measured",
    "third_party_observed",
    "operator_supplied",
    "modeled_proxy",
    "synthetic",
    "assumption",
    "missing",
)

# Lower rank = stronger evidence. Used to report the weakest input behind an estimate.
# A cited planning assumption ranks above a formula proxy; invented (synthetic) values rank last.
EVIDENCE_RANK = {e: i for i, e in enumerate((
    "measured", "third_party_observed", "operator_supplied",
    "assumption", "modeled_proxy", "synthetic", "missing"))}

# Short, colour-independent labels for tables and memos.
EVIDENCE_LABEL = {
    "measured": "MEASURED",
    "third_party_observed": "3RD-PARTY OBS",
    "operator_supplied": "OPERATOR",
    "modeled_proxy": "PROXY",
    "synthetic": "SYNTHETIC",
    "assumption": "ASSUMPTION",
    "missing": "MISSING",
}

LONG_COLUMNS = [
    "site_id", "field", "value", "unit", "source",
    "as_of_date", "evidence_type", "uncertainty_pct", "notes",
]


@dataclass(frozen=True)
class FieldSpec:
    unit: str                      # "{cur}" is replaced by the portfolio currency
    kind: str = "number"           # number | text | flag
    required: bool = True
    min: Optional[float] = None
    max: Optional[float] = None
    description: str = ""


# Data dictionary. Ranges are physical/plausibility bounds, not targets.
FIELD_SPECS: Dict[str, FieldSpec] = {
    "site_name": FieldSpec("-", "text", True, description="Human-readable label"),
    "latitude": FieldSpec("deg", min=-90, max=90, description="WGS84 latitude"),
    "longitude": FieldSpec("deg", min=-180, max=180, description="WGS84 longitude"),
    "currency": FieldSpec("-", "text", True, description="ISO 4217 code for all money fields"),
    "ghi_kwh_m2_day": FieldSpec("kWh/m2/day", min=1.0, max=8.0,
                                description="Long-term mean global horizontal irradiance"),
    "load_kw_avg": FieldSpec("kW", min=0.05, max=30.0,
                             description="Average site electrical load (flat profile assumed)"),
    "daytime_load_fraction": FieldSpec("fraction", required=False, min=0.2, max=0.8,
                                       description="Share of daily load during PV production hours"),
    "grid_hours_per_day": FieldSpec("h/day", min=0, max=24,
                                    description="Mean hours/day the grid supplies the site"),
    "diesel_l_per_day": FieldSpec("L/day", required=False, min=0, max=500,
                                  description="Generator fuel use; modeled from load if missing"),
    "diesel_price_per_l": FieldSpec("{cur}/L", min=0, description="Delivered diesel price"),
    "grid_tariff_per_kwh": FieldSpec("{cur}/kWh", min=0, description="Grid energy tariff"),
    "diesel_ef_kg_per_l": FieldSpec("kgCO2/L", min=2.4, max=2.8,
                                    description="Diesel combustion emission factor"),
    "grid_ef_kg_per_kwh": FieldSpec("kgCO2/kWh", min=0.0, max=1.5,
                                    description="Grid emission factor"),
    "pv_capex_per_kwp": FieldSpec("{cur}/kWp", min=0, description="Installed PV cost"),
    "battery_capex_per_kwh": FieldSpec("{cur}/kWh", min=0, description="Installed battery cost"),
    "fixed_install_capex": FieldSpec("{cur}", required=False, min=0,
                                     description="Per-site mobilisation / BOS cost for any retrofit"),
    "max_pv_kwp": FieldSpec("kWp", min=0, max=200, description="Space/structural PV limit"),
    "max_battery_kwh": FieldSpec("kWh", min=0, max=500, description="Shelter/space battery limit"),
    "service_population_proxy": FieldSpec("people", required=False, min=0,
                                          description="Population near site; overlaps between sites "
                                                      "are NOT removed, so never sum across sites"),
    "road_distance_km": FieldSpec("km", required=False, min=0, max=200,
                                  description="Distance to nearest road (access proxy)"),
}

# Money fields must use the declared currency in their unit.
MONEY_FIELDS = [k for k, s in FIELD_SPECS.items() if "{cur}" in s.unit]

# Plausibility caps per currency for prices; values outside are errors ("invalid tariffs").
PRICE_CAPS = {
    "USD": {"diesel_price_per_l": 5.0, "grid_tariff_per_kwh": 1.0},
    "IDR": {"diesel_price_per_l": 80_000.0, "grid_tariff_per_kwh": 15_000.0},
}


@dataclass(frozen=True)
class FieldValue:
    value: object
    unit: str
    source: str
    as_of_date: Optional[str]
    evidence_type: str
    uncertainty_pct: Optional[float] = None
    notes: str = ""

    @property
    def is_missing(self) -> bool:
        return self.evidence_type == "missing" or self.value is None

    def bounds(self) -> Tuple[float, float]:
        """(low, high) using the symmetric uncertainty, or (value, value)."""
        v = float(self.value)
        u = (self.uncertainty_pct or 0.0) / 100.0
        return v * (1 - u), v * (1 + u)


@dataclass
class SiteFeatures:
    site_id: str
    fields: Dict[str, FieldValue] = field(default_factory=dict)

    def get(self, name: str, default=None):
        fv = self.fields.get(name)
        if fv is None or fv.is_missing:
            return default
        return fv.value

    def evidence(self, name: str) -> str:
        fv = self.fields.get(name)
        return "missing" if fv is None else fv.evidence_type

    def uncertainty(self, name: str) -> float:
        fv = self.fields.get(name)
        return float(fv.uncertainty_pct or 0.0) if fv is not None else 0.0


@dataclass(frozen=True)
class Issue:
    severity: str        # error | warning
    site_id: str
    field: str
    message: str


def _is_blank(v) -> bool:
    return v is None or (isinstance(v, float) and math.isnan(v)) or (isinstance(v, str) and v.strip() == "")


def _parse_date(s) -> Optional[str]:
    if _is_blank(s):
        return None
    s = str(s).strip()
    try:
        date.fromisoformat(s)
        return s
    except ValueError:
        return "INVALID"


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    r = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def validate_portfolio(records: pd.DataFrame, duplicate_radius_m: float = 25.0
                       ) -> Tuple[List[SiteFeatures], List[Issue]]:
    """
    Validate long-format records. Returns (valid_sites, issues).
    Sites with any error are excluded from valid_sites but remain listed in issues.
    """
    issues: List[Issue] = []
    missing_cols = [c for c in LONG_COLUMNS if c not in records.columns and c != "notes"]
    if missing_cols:
        return [], [Issue("error", "*", "*", f"Missing columns: {missing_cols}")]

    df = records.copy()
    df["site_id"] = df["site_id"].astype(str).str.strip()
    df["field"] = df["field"].astype(str).str.strip()

    dup = df[df.duplicated(["site_id", "field"], keep=False)]
    for (sid, f), _ in dup.groupby(["site_id", "field"]):
        issues.append(Issue("error", sid, f, "Duplicate rows for the same site and field"))

    sites: Dict[str, SiteFeatures] = {}
    for _, r in df.drop_duplicates(["site_id", "field"], keep="first").iterrows():
        sid, fname = r["site_id"], r["field"]
        spec = FIELD_SPECS.get(fname)
        if spec is None:
            issues.append(Issue("warning", sid, fname, "Unknown field ignored"))
            continue
        ev = str(r["evidence_type"]).strip() if not _is_blank(r["evidence_type"]) else ""
        if ev not in EVIDENCE_TYPES:
            issues.append(Issue("error", sid, fname, f"Invalid evidence_type '{ev}'"))
            continue
        raw = r["value"]
        if ev == "missing":
            value = None
        elif _is_blank(raw):
            issues.append(Issue("error", sid, fname, "Blank value must be labelled evidence_type=missing"))
            continue
        elif spec.kind == "number":
            try:
                value = float(raw)
            except (TypeError, ValueError):
                issues.append(Issue("error", sid, fname, f"Non-numeric value '{raw}'"))
                continue
            if not math.isfinite(value):
                issues.append(Issue("error", sid, fname, "Non-finite value"))
                continue
        else:
            value = str(raw).strip()

        as_of = _parse_date(r["as_of_date"])
        if as_of == "INVALID":
            issues.append(Issue("error", sid, fname, f"as_of_date '{r['as_of_date']}' is not ISO YYYY-MM-DD"))
            as_of = None
        source = "" if _is_blank(r["source"]) else str(r["source"]).strip()
        if ev in ("measured", "third_party_observed", "operator_supplied") and (not source or as_of is None):
            issues.append(Issue("error", sid, fname, f"{ev} values need a source and as_of_date"))
        unc = None if _is_blank(r["uncertainty_pct"]) else float(r["uncertainty_pct"])
        if unc is not None and not (0 <= unc <= 200):
            issues.append(Issue("error", sid, fname, f"uncertainty_pct {unc} outside 0-200"))
        notes = "" if _is_blank(r.get("notes")) else str(r.get("notes"))
        sites.setdefault(sid, SiteFeatures(sid)).fields[fname] = FieldValue(
            value, "" if _is_blank(r["unit"]) else str(r["unit"]).strip(), source, as_of, ev, unc, notes)

    currencies = {s.get("currency") for s in sites.values() if s.get("currency")}
    if len(currencies) > 1:
        issues.append(Issue("error", "*", "currency",
                            f"Mixed currencies {sorted(currencies)}; convert to one currency before upload"))

    for sid, s in sites.items():
        cur = s.get("currency")
        if cur is not None and not re.fullmatch(r"[A-Z]{3}", str(cur)):
            issues.append(Issue("error", sid, "currency", f"'{cur}' is not an ISO 4217 code"))
        for fname, spec in FIELD_SPECS.items():
            fv = s.fields.get(fname)
            if fv is None or fv.is_missing:
                if spec.required:
                    issues.append(Issue("error", sid, fname, "Required field missing"))
                continue
            expected_unit = spec.unit.replace("{cur}", str(cur))
            if fv.unit != expected_unit:
                issues.append(Issue("error", sid, fname, f"Unit '{fv.unit}' != expected '{expected_unit}'"))
            if spec.kind == "number":
                v = float(fv.value)
                if spec.min is not None and v < spec.min:
                    issues.append(Issue("error", sid, fname, f"{v} below minimum {spec.min}"))
                if spec.max is not None and v > spec.max:
                    issues.append(Issue("error", sid, fname, f"{v} above maximum {spec.max}"))
        lat, lon = s.get("latitude"), s.get("longitude")
        if lat is not None and lon is not None and abs(lat) < 1e-9 and abs(lon) < 1e-9:
            issues.append(Issue("error", sid, "latitude", "Coordinates (0,0) are a null-island placeholder"))
        caps = PRICE_CAPS.get(str(cur), {})
        for fname, cap in caps.items():
            v = s.get(fname)
            if v is not None and v > cap:
                issues.append(Issue("error", sid, fname, f"{v} {cur} exceeds plausibility cap {cap}"))
        if (s.get("grid_hours_per_day") or 0) > 0 and (s.get("grid_tariff_per_kwh") or 0) <= 0:
            issues.append(Issue("error", sid, "grid_tariff_per_kwh",
                                "Grid-supplied site needs a positive tariff"))
        if s.get("diesel_l_per_day") is not None and s.get("load_kw_avg"):
            # Generator efficiency below 1 or above 4.5 kWh/L is implausible for site gensets.
            d = s.get("diesel_l_per_day")
            diesel_need_kwh = s.get("load_kw_avg") * (24 - (s.get("grid_hours_per_day") or 0))
            if d > 0 and diesel_need_kwh > 0 and not (1.0 <= diesel_need_kwh / d <= 4.5):
                issues.append(Issue("warning", sid, "diesel_l_per_day",
                                    f"Implied genset yield {diesel_need_kwh / d:.2f} kWh/L is unusual"))
            if d > 0 and diesel_need_kwh == 0:
                issues.append(Issue("warning", sid, "diesel_l_per_day",
                                    "Diesel use reported for a 24 h grid site (backup tests?)"))

    # Duplicate towers: distinct site_ids at (nearly) the same coordinates.
    located = [(sid, s.get("latitude"), s.get("longitude")) for sid, s in sites.items()
               if s.get("latitude") is not None and s.get("longitude") is not None]
    for i in range(len(located)):
        for j in range(i + 1, len(located)):
            a, b = located[i], located[j]
            if haversine_m(a[1], a[2], b[1], b[2]) <= duplicate_radius_m:
                for sid, other in ((a[0], b[0]), (b[0], a[0])):
                    issues.append(Issue("error", sid, "latitude",
                                        f"Possible duplicate tower of {other} (within {duplicate_radius_m:.0f} m)"))

    bad = {i.site_id for i in issues if i.severity == "error"}
    if "*" in bad:
        bad = set(sites)  # portfolio-level errors block every site
    valid = [s for sid, s in sites.items() if sid not in bad]
    return valid, issues


def issues_frame(issues: List[Issue]) -> pd.DataFrame:
    return pd.DataFrame([i.__dict__ for i in issues], columns=["severity", "site_id", "field", "message"])


def evidence_matrix(sites: List[SiteFeatures]) -> pd.DataFrame:
    """site × field table of text evidence labels (colour-independent)."""
    rows = []
    for s in sites:
        row = {"site_id": s.site_id}
        for fname in FIELD_SPECS:
            row[fname] = EVIDENCE_LABEL[s.evidence(fname)]
        rows.append(row)
    return pd.DataFrame(rows)


def sites_to_wide(sites: List[SiteFeatures]) -> pd.DataFrame:
    """Values plus '<field>__evidence' columns, one row per site."""
    rows = []
    for s in sites:
        row = {"site_id": s.site_id}
        for fname in FIELD_SPECS:
            row[fname] = s.get(fname)
            row[f"{fname}__evidence"] = s.evidence(fname)
        rows.append(row)
    return pd.DataFrame(rows)


def load_portfolio_csv(path_or_buffer) -> pd.DataFrame:
    return pd.read_csv(path_or_buffer, dtype={"site_id": str, "value": str})
