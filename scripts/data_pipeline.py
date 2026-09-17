"""
SUNTOWER-AI Data Pipeline v2
Processes tower locations and generates geospatial features for scoring.
Uses satellite-derived proxies and open data models.

All towers are candidates for solar energy transition — not just off-grid.
Grid-connected towers benefit from reduced electricity costs and carbon footprint.
Off-grid/weak-grid towers benefit additionally from diesel displacement.
"""

import pandas as pd
import numpy as np
import json
import os
import math

# -------------------------------------------------------------------
# Constants
# -------------------------------------------------------------------
DIESEL_LITRES_PER_DAY_LOW = 5
DIESEL_LITRES_PER_DAY_HIGH = 20
DIESEL_PRICE_IDR = 13_300
DIESEL_PRICE_USD = 0.82
GRID_ELECTRICITY_COST_USD_KWH = 0.08  # Indonesia average
CO2_PER_LITRE_DIESEL = 2.68  # kg CO₂
CO2_PER_KWH_GRID = 0.76     # kg CO₂/kWh (Indonesia grid average)
SOLAR_OFFSET = 0.70
CAPEX_OFFGRID_USD = 45_000   # Full solar-hybrid + battery
CAPEX_GRID_SOLAR_USD = 25_000  # Rooftop solar for grid-connected
EARTH_RADIUS_KM = 6371.0

# Tower power consumption estimates (kWh/day)
TOWER_POWER_SMALL = 15   # Small tower, ~0.6 kW avg
TOWER_POWER_MEDIUM = 40  # Medium tower, ~1.7 kW avg
TOWER_POWER_LARGE = 80   # Large multi-tenant tower, ~3.3 kW avg

# -------------------------------------------------------------------
# Haversine distance
# -------------------------------------------------------------------
def haversine(lat1, lon1, lat2, lon2):
    lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


# -------------------------------------------------------------------
# Solar Irradiance Model (GHI)
# Indonesia equatorial: 4.2 - 5.8 kWh/m²/day
# West Java: ~4.5 - 5.3 kWh/m²/day
# -------------------------------------------------------------------
def estimate_ghi(lat, lon, elevation):
    base_ghi = 5.0
    lat_effect = -0.05 * abs(lat + 6.7)
    if elevation < 1500:
        elev_effect = 0.0003 * elevation
    else:
        elev_effect = 0.45 - 0.0001 * (elevation - 1500)
    lon_effect = 0.1 * math.sin((lon - 107.0) * 2.0)
    noise = 0.15 * math.sin(lat * 100 + lon * 50)
    ghi = base_ghi + lat_effect + elev_effect + lon_effect + noise
    return max(3.8, min(5.8, round(ghi, 2)))


# -------------------------------------------------------------------
# Elevation Model (West Java topography)
# -------------------------------------------------------------------
def estimate_elevation(lat, lon):
    dist_from_bandung = haversine(lat, lon, -6.9, 107.6)
    if lat > -6.5:
        base = 50 + 30 * abs(lon - 107.5)
    elif lat < -7.2:
        base = 400 + 200 * abs(lat + 7.0)
    else:
        base = 700 - 15 * dist_from_bandung
    variation = 80 * math.sin(lat * 50) + 60 * math.cos(lon * 40)
    return max(5, min(2200, round(base + variation)))


# -------------------------------------------------------------------
# Population Density (5km buffer)
# -------------------------------------------------------------------
def estimate_population_5km(lat, lon):
    urban_centers = [
        (-6.917, 107.619, 2_500_000, "Bandung"),
        (-6.708, 106.845, 800_000, "Bogor"),
        (-6.732, 108.552, 300_000, "Cirebon"),
        (-6.600, 106.800, 500_000, "Depok"),
        (-6.887, 107.510, 200_000, "Cimahi"),
        (-6.710, 107.310, 150_000, "Purwakarta"),
        (-7.330, 108.220, 200_000, "Tasikmalaya"),
        (-6.816, 108.217, 150_000, "Majalengka"),
        (-6.730, 107.130, 120_000, "Subang"),
    ]
    total_pop = 0
    for clat, clon, cpop, _ in urban_centers:
        dist = haversine(lat, lon, clat, clon)
        if dist < 50:
            influence = cpop * max(0, 1 - (dist / 50) ** 1.5)
            total_pop += influence
    base_rural = 8000 + 4000 * math.sin(lat * 30 + lon * 20)
    pop = total_pop + max(2000, base_rural)
    variation = 1500 * math.sin(lat * 80 + lon * 60)
    return max(500, int(pop + variation))


# -------------------------------------------------------------------
# Nighttime Lights (VIIRS proxy)
# -------------------------------------------------------------------
def estimate_nightlight(lat, lon, population_5km):
    if population_5km > 200_000:
        base = 50 + 10 * math.log10(population_5km)
    elif population_5km > 50_000:
        base = 20 + 5 * math.log10(population_5km)
    else:
        base = 2 + 2 * math.log10(max(1, population_5km))
    variation = 3 * math.sin(lat * 70 + lon * 40)
    return max(0.1, min(63.0, round(base + variation, 1)))


# -------------------------------------------------------------------
# Grid reliability classification
# Based on nightlight intensity + population density
# -------------------------------------------------------------------
def classify_grid_status(nightlight, population_5km, elevation):
    """
    Classify grid reliability status:
    0 = Strong grid (urban core)
    1 = Moderate grid (suburban, semi-reliable)
    2 = Weak grid (peri-urban/rural, frequent outages)
    3 = Off-grid (no reliable grid connection)
    """
    if nightlight > 40 and population_5km > 100_000:
        return 0  # Strong grid
    elif nightlight > 25 and population_5km > 50_000:
        return 1  # Moderate grid
    elif nightlight > 12 and population_5km > 15_000:
        return 2  # Weak grid (frequent outages, backup needed)
    else:
        return 3  # Off-grid


def grid_status_label(status):
    return {0: "Strong Grid", 1: "Moderate Grid", 2: "Weak Grid", 3: "Off-Grid"}[status]


# -------------------------------------------------------------------
# Road Distance Proxy
# -------------------------------------------------------------------
def estimate_road_distance(lat, lon, population_5km):
    if population_5km > 100_000:
        base_dist = 0.2
    elif population_5km > 30_000:
        base_dist = 1.0
    elif population_5km > 10_000:
        base_dist = 3.0
    else:
        base_dist = 8.0
    variation = 2.0 * abs(math.sin(lat * 90 + lon * 45))
    return max(0.05, round(base_dist + variation, 2))


# -------------------------------------------------------------------
# Energy / Diesel / Cost Estimation
# -------------------------------------------------------------------
def estimate_tower_energy(tower_height, grid_status):
    """Estimate daily energy consumption in kWh and diesel backup needs."""
    # Base power from tower size
    if tower_height <= 25:
        daily_kwh = TOWER_POWER_SMALL
    elif tower_height <= 45:
        daily_kwh = TOWER_POWER_MEDIUM
    else:
        daily_kwh = TOWER_POWER_LARGE

    # Diesel backup proportion based on grid reliability
    diesel_fraction = {
        0: 0.05,   # 5% backup (strong grid, rare outages)
        1: 0.15,   # 15% backup (moderate grid)
        2: 0.40,   # 40% backup (weak grid, frequent outages)
        3: 1.00,   # 100% diesel (off-grid)
    }[grid_status]

    diesel_kwh_day = daily_kwh * diesel_fraction
    # Diesel generator efficiency ~3 kWh/litre
    diesel_litres_day = diesel_kwh_day / 3.0

    grid_kwh_day = daily_kwh * (1 - diesel_fraction)

    return daily_kwh, diesel_litres_day, grid_kwh_day


# -------------------------------------------------------------------
# Main Pipeline
# -------------------------------------------------------------------
def process_tower_data(input_path: str, output_path: str):
    print("=" * 60)
    print("SUNTOWER-AI Data Pipeline v2")
    print("=" * 60)

    # 1. Load tower data
    print("\n[1/8] Loading tower data...")
    df = pd.read_csv(input_path)
    print(f"  Loaded {len(df)} towers")

    # Clean data
    df = df.dropna(subset=['long', 'lat'])
    df['long'] = pd.to_numeric(df['long'], errors='coerce')
    df['lat'] = pd.to_numeric(df['lat'], errors='coerce')
    df = df.dropna(subset=['long', 'lat'])

    # Fix swapped lat/lon
    swapped_mask = (df['long'] < 0) & (df['lat'] > 0)
    if swapped_mask.any():
        n = swapped_mask.sum()
        print(f"  ⚠ Detected {n} rows with swapped lat/lon — auto-correcting")
        df.loc[swapped_mask, ['long', 'lat']] = df.loc[swapped_mask, ['lat', 'long']].values

    # Remove outliers
    valid_mask = (
        (df['lat'] >= -11) & (df['lat'] <= 6) &
        (df['long'] >= 95) & (df['long'] <= 141)
    )
    n_invalid = (~valid_mask).sum()
    if n_invalid > 0:
        print(f"  ⚠ Removing {n_invalid} rows with invalid coordinates")
        df = df[valid_mask]

    df['tower_height'] = pd.to_numeric(df['tinggi_tower'], errors='coerce').fillna(30)
    print(f"  After cleaning: {len(df)} towers")
    print(f"  Lat range: {df['lat'].min():.4f} to {df['lat'].max():.4f}")
    print(f"  Lon range: {df['long'].min():.4f} to {df['long'].max():.4f}")

    # 2. Elevation
    print("\n[2/8] Estimating elevation...")
    df['elevation_m'] = df.apply(lambda r: estimate_elevation(r['lat'], r['long']), axis=1)
    print(f"  Range: {df['elevation_m'].min()}m - {df['elevation_m'].max()}m")

    # 3. GHI
    print("\n[3/8] Estimating solar irradiance (GHI)...")
    df['ghi_kwh_m2_day'] = df.apply(
        lambda r: estimate_ghi(r['lat'], r['long'], r['elevation_m']), axis=1
    )
    print(f"  Range: {df['ghi_kwh_m2_day'].min():.2f} - {df['ghi_kwh_m2_day'].max():.2f} kWh/m²/day")

    # 4. Population
    print("\n[4/8] Estimating population (5km radius)...")
    df['population_5km'] = df.apply(
        lambda r: estimate_population_5km(r['lat'], r['long']), axis=1
    )
    print(f"  Range: {df['population_5km'].min():,} - {df['population_5km'].max():,}")

    # 5. Nighttime lights + grid status
    print("\n[5/8] Classifying grid reliability...")
    df['nightlight_intensity'] = df.apply(
        lambda r: estimate_nightlight(r['lat'], r['long'], r['population_5km']), axis=1
    )
    df['grid_status'] = df.apply(
        lambda r: classify_grid_status(r['nightlight_intensity'], r['population_5km'], r['elevation_m']),
        axis=1
    )
    df['grid_status_label'] = df['grid_status'].apply(grid_status_label)
    df['is_off_grid'] = (df['grid_status'] >= 2).astype(int)  # Weak grid + off-grid are candidates

    for status in range(4):
        count = (df['grid_status'] == status).sum()
        label = grid_status_label(status)
        print(f"  {label}: {count} towers ({count/len(df)*100:.1f}%)")
    print(f"  Solar candidates (weak grid + off-grid): {df['is_off_grid'].sum()}")

    # 6. Road distance
    print("\n[6/8] Estimating road distance...")
    df['road_distance_km'] = df.apply(
        lambda r: estimate_road_distance(r['lat'], r['long'], r['population_5km']), axis=1
    )

    # 7. Energy and cost estimation
    print("\n[7/8] Estimating energy consumption and costs...")
    energy_data = df.apply(
        lambda r: estimate_tower_energy(r['tower_height'], r['grid_status']), axis=1
    )
    df['daily_kwh'] = energy_data.apply(lambda x: x[0])
    df['diesel_litres_day'] = energy_data.apply(lambda x: x[1])
    df['grid_kwh_day'] = energy_data.apply(lambda x: x[2])

    df['diesel_litres_year'] = df['diesel_litres_day'] * 365
    df['diesel_cost_usd_year'] = df['diesel_litres_year'] * DIESEL_PRICE_USD
    df['grid_cost_usd_year'] = df['grid_kwh_day'] * 365 * GRID_ELECTRICITY_COST_USD_KWH
    df['total_energy_cost_usd_year'] = df['diesel_cost_usd_year'] + df['grid_cost_usd_year']

    df['co2_diesel_tonnes_year'] = df['diesel_litres_year'] * CO2_PER_LITRE_DIESEL / 1000
    df['co2_grid_tonnes_year'] = df['grid_kwh_day'] * 365 * CO2_PER_KWH_GRID / 1000
    df['co2_total_tonnes_year'] = df['co2_diesel_tonnes_year'] + df['co2_grid_tonnes_year']

    # Solar savings potential
    df['diesel_savings_usd_year'] = df['diesel_cost_usd_year'] * SOLAR_OFFSET
    df['grid_savings_usd_year'] = df['grid_cost_usd_year'] * SOLAR_OFFSET * 0.5  # Partial grid offset
    df['total_savings_usd_year'] = df['diesel_savings_usd_year'] + df['grid_savings_usd_year']

    df['co2_avoided_tonnes_year'] = (
        df['co2_diesel_tonnes_year'] * SOLAR_OFFSET +
        df['co2_grid_tonnes_year'] * SOLAR_OFFSET * 0.5
    )

    # CAPEX based on grid status
    df['capex_usd'] = df['grid_status'].apply(
        lambda s: CAPEX_OFFGRID_USD if s >= 2 else CAPEX_GRID_SOLAR_USD
    )

    candidates = df[df['is_off_grid'] == 1]
    print(f"\n  Solar candidates summary:")
    print(f"    Towers: {len(candidates)}")
    print(f"    Total diesel: {candidates['diesel_litres_year'].sum():,.0f} L/yr")
    print(f"    Total energy cost: ${candidates['total_energy_cost_usd_year'].sum():,.0f}/yr")
    print(f"    Total CO₂: {candidates['co2_total_tonnes_year'].sum():,.0f} t/yr")
    print(f"    Potential savings: ${candidates['total_savings_usd_year'].sum():,.0f}/yr")

    # 8. Connectivity equity index
    print("\n[8/8] Computing connectivity equity index...")
    nl_max = df['nightlight_intensity'].max()
    nl_min = df['nightlight_intensity'].min()
    if nl_max > nl_min:
        df['connectivity_gap'] = 1 - (df['nightlight_intensity'] - nl_min) / (nl_max - nl_min)
    else:
        df['connectivity_gap'] = 0.5

    pop_max = df['population_5km'].max()
    df['population_norm'] = df['population_5km'] / pop_max if pop_max > 0 else 0
    df['connectivity_equity'] = df['population_norm'] * df['connectivity_gap']

    # Select output columns
    output_cols = [
        'id', 'nama_provinsi', 'bps_nama_kabupaten_kota', 'bps_nama_kecamatan',
        'pemilik_menara', 'lokasi_menara', 'long', 'lat',
        'struktur_tower', 'tower_height', 'elevation_m',
        'ghi_kwh_m2_day', 'population_5km', 'nightlight_intensity',
        'grid_status', 'grid_status_label', 'is_off_grid', 'road_distance_km',
        'daily_kwh', 'diesel_litres_day', 'diesel_litres_year',
        'diesel_cost_usd_year', 'grid_cost_usd_year', 'total_energy_cost_usd_year',
        'co2_diesel_tonnes_year', 'co2_grid_tonnes_year', 'co2_total_tonnes_year',
        'diesel_savings_usd_year', 'grid_savings_usd_year', 'total_savings_usd_year',
        'co2_avoided_tonnes_year', 'capex_usd',
        'connectivity_gap', 'connectivity_equity'
    ]

    df_out = df[[c for c in output_cols if c in df.columns]].copy()
    df_out.to_csv(output_path, index=False)

    print(f"\n{'=' * 60}")
    print(f"Pipeline complete. Output: {output_path}")
    print(f"Total towers: {len(df_out)}")
    print(f"Solar candidates: {df_out['is_off_grid'].sum()}")
    print(f"{'=' * 60}")

    return df_out


if __name__ == "__main__":
    base = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.join(base, "..", "documents source", "sources",
                              "bootcamp 2", "GeoAI Dataset",
                              "lokasi_menara_telekomunikasi.csv")
    output_file = os.path.join(base, "..", "data", "towers_enriched.csv")
    process_tower_data(input_file, output_file)
