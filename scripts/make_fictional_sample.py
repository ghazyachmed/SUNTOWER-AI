"""
Generate data/sample_portfolio_fictional.csv — an explicitly FICTIONAL 11-tower
portfolio in long format. No value describes a real tower, operator or place.

* Site-specific values are evidence_type=synthetic (invented for the demo).
* GHI for three sites is evidence_type=modeled_proxy: computed with the legacy
  data_pipeline.estimate_ghi() formula (a formula, not a satellite observation).
* Price and emission constants are evidence_type=assumption, citing where the
  constant came from. FICT-04 has diesel use labelled missing (modeled from load).
* FICT-11 contains a deliberate error (GHI 12.5) so the exclusion path is exercised.

Coordinates are points on a 0.1-degree grid chosen for display only.
"""

from __future__ import annotations

import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data_pipeline import estimate_elevation, estimate_ghi  # noqa: E402

AS_OF = "2026-11-01"
SYN = ("synthetic", "Fictional demo value (make_fictional_sample.py)", AS_OF)

# site, lat, lon, load_kw, grid_h, diesel_l_day (None=missing), ghi (None=proxy), max_pv, max_batt, pop, road_km
SITES = [
    ("FICT-01", -7.0, 107.0, 1.2, 0.0, 9.6, 4.9, 12, 20, 6_000, 6.5),
    ("FICT-02", -7.0, 107.1, 2.5, 8.0, 13.3, 4.7, 20, 30, 15_000, 3.0),
    ("FICT-03", -7.0, 107.2, 3.5, 20.0, 4.0, None, 25, 30, 60_000, 0.4),
    ("FICT-04", -7.1, 107.0, 1.8, 12.0, None, 4.8, 10, 15, 9_000, 4.2),
    ("FICT-05", -7.1, 107.1, 1.0, 24.0, 0.0, None, 8, 10, 80_000, 0.2),
    ("FICT-06", -7.1, 107.2, 2.0, 0.0, 16.0, 5.1, 0, 20, 4_000, 9.0),
    ("FICT-07", -7.2, 107.0, 3.0, 4.0, 20.0, 4.6, 30, 0, 12_000, 2.5),
    ("FICT-08", -7.2, 107.1, 1.5, 16.0, 3.0, None, 10, 12, 25_000, 1.1),
    ("FICT-09", -7.2, 107.2, 2.2, 0.0, 17.6, 5.0, 18, 25, 3_000, 12.0),
    ("FICT-10", -7.3, 107.0, 1.6, 10.0, 7.5, 4.9, 12, 16, 18_000, 2.0),
    ("FICT-11", -7.3, 107.1, 1.4, 6.0, 8.0, 12.5, 10, 12, 7_000, 3.5),
]

ASSUMED = [
    ("currency", "USD", "-", "Demo currency", None),
    ("diesel_price_per_l", 0.82, "USD/L", "Legacy constant DIESEL_PRICE_USD in data_pipeline.py (source not cited)", 20),
    ("grid_tariff_per_kwh", 0.08, "USD/kWh", "Legacy constant GRID_ELECTRICITY_COST_USD_KWH (source not cited)", 15),
    ("diesel_ef_kg_per_l", 2.68, "kgCO2/L", "Legacy constant CO2_PER_LITRE_DIESEL; consistent with IPCC 2006 "
                                             "default for gas/diesel oil (not re-verified here)", 3),
    ("grid_ef_kg_per_kwh", 0.76, "kgCO2/kWh", "Legacy constant CO2_PER_KWH_GRID (source not cited)", 15),
    ("pv_capex_per_kwp", 900, "USD/kWp", "Planning placeholder; replace with vendor quotes", 25),
    ("battery_capex_per_kwh", 400, "USD/kWh", "Planning placeholder; replace with vendor quotes", 25),
    ("fixed_install_capex", 3000, "USD", "Planning placeholder for mobilisation/BOS", 40),
]


def rows():
    out = []
    for (sid, lat, lon, load, grid_h, diesel, ghi, max_pv, max_batt, pop, road) in SITES:
        def add(field, value, unit, ev=SYN, unc=None, notes=""):
            out.append([sid, field, value, unit, ev[1], ev[2], ev[0], "" if unc is None else unc, notes])

        add("site_name", f"Fictional tower {sid[-2:]}", "-")
        add("latitude", lat, "deg", notes="FICTIONAL coordinate on display grid")
        add("longitude", lon, "deg", notes="FICTIONAL coordinate on display grid")
        add("load_kw_avg", load, "kW", unc=15)
        add("grid_hours_per_day", grid_h, "h/day", unc=20 if 0 < grid_h < 24 else None)
        if diesel is None:
            out.append([sid, "diesel_l_per_day", "", "L/day", "", "", "missing", "",
                        "Not reported; modeled from load and grid hours"])
        else:
            add("diesel_l_per_day", diesel, "L/day", unc=20)
        if ghi is None:
            elev = estimate_elevation(lat, lon)
            add("ghi_kwh_m2_day", estimate_ghi(lat, lon, elev), "kWh/m2/day",
                ev=("modeled_proxy", "Legacy formula data_pipeline.estimate_ghi(lat, lon, elevation proxy)", AS_OF),
                unc=15, notes="Formula output, not a satellite observation")
        else:
            add("ghi_kwh_m2_day", ghi, "kWh/m2/day", unc=10)
        add("max_pv_kwp", max_pv, "kWp")
        add("max_battery_kwh", max_batt, "kWh")
        add("service_population_proxy", pop, "people", unc=50, notes="Overlaps not removed; do not sum")
        add("road_distance_km", road, "km", unc=30)
        for field, value, unit, src, unc in ASSUMED:
            add(field, value, unit, ev=("assumption", src, AS_OF), unc=unc)
    return out


def main(path=None):
    path = path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data",
                                "sample_portfolio_fictional.csv")
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["site_id", "field", "value", "unit", "source", "as_of_date",
                    "evidence_type", "uncertainty_pct", "notes"])
        w.writerows(rows())
    print(f"Wrote {path}")


if __name__ == "__main__":
    main()
