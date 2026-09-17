"""
SUNTOWER-AI Scoring Engine v2
Multi-criteria GeoAI scoring with configurable weights and budget-constrained optimization.
"""

import pandas as pd
import numpy as np


# -------------------------------------------------------------------
# Default Weights (must sum to 1.0)
# -------------------------------------------------------------------
DEFAULT_WEIGHTS = {
    'solar_potential': 0.25,
    'energy_savings': 0.25,
    'carbon_avoided': 0.20,
    'connectivity_equity': 0.20,
    'access_feasibility': 0.10,
}

SCENARIO_WEIGHTS = {
    'balanced': {
        'solar_potential': 0.20,
        'energy_savings': 0.20,
        'carbon_avoided': 0.20,
        'connectivity_equity': 0.25,
        'access_feasibility': 0.15,
    },
    'economic': {
        'solar_potential': 0.20,
        'energy_savings': 0.40,
        'carbon_avoided': 0.10,
        'connectivity_equity': 0.15,
        'access_feasibility': 0.15,
    },
    'carbon': {
        'solar_potential': 0.25,
        'energy_savings': 0.10,
        'carbon_avoided': 0.40,
        'connectivity_equity': 0.15,
        'access_feasibility': 0.10,
    },
    'equity': {
        'solar_potential': 0.15,
        'energy_savings': 0.10,
        'carbon_avoided': 0.15,
        'connectivity_equity': 0.45,
        'access_feasibility': 0.15,
    },
}


def normalize_column(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    """Min-max normalize a column to 0-1 range."""
    vmin = series.min()
    vmax = series.max()
    if vmax == vmin:
        return pd.Series(0.5, index=series.index)
    norm = (series - vmin) / (vmax - vmin)
    if not higher_is_better:
        norm = 1 - norm
    return norm


def compute_scores(df: pd.DataFrame, weights: dict = None) -> pd.DataFrame:
    """
    Compute SUNTOWER scores for all towers.
    """
    if weights is None:
        weights = DEFAULT_WEIGHTS

    result = df.copy()

    # Solar potential: higher GHI = better
    result['score_solar'] = normalize_column(result['ghi_kwh_m2_day'], higher_is_better=True)

    # Energy savings: higher total savings = better priority
    result['score_savings'] = normalize_column(result['total_savings_usd_year'], higher_is_better=True)

    # Carbon avoided: more CO₂ avoided = better
    result['score_carbon'] = normalize_column(result['co2_avoided_tonnes_year'], higher_is_better=True)

    # Connectivity equity: higher equity score = more underserved + more population
    result['score_equity'] = normalize_column(result['connectivity_equity'], higher_is_better=True)

    # Access feasibility: closer to roads = easier access = better
    result['score_access'] = normalize_column(result['road_distance_km'], higher_is_better=False)

    # Weighted composite score
    result['suntower_score'] = (
        weights['solar_potential'] * result['score_solar'] +
        weights['energy_savings'] * result['score_savings'] +
        weights['carbon_avoided'] * result['score_carbon'] +
        weights['connectivity_equity'] * result['score_equity'] +
        weights['access_feasibility'] * result['score_access']
    )

    # Scale to 0-10
    score_min = result['suntower_score'].min()
    score_max = result['suntower_score'].max()
    if score_max > score_min:
        result['suntower_score_10'] = (
            (result['suntower_score'] - score_min) / (score_max - score_min) * 10
        )
    else:
        result['suntower_score_10'] = 5.0

    result['suntower_score_10'] = result['suntower_score_10'].round(1)

    # Rank
    result['rank'] = result['suntower_score_10'].rank(ascending=False, method='min').astype(int)

    return result


def budget_allocation(df: pd.DataFrame, budget_usd: float, candidates_only: bool = True) -> pd.DataFrame:
    """
    Select towers for solarisation within budget constraint.
    Uses greedy ranking approach (highest score first).
    """
    if candidates_only:
        candidates = df[df['is_off_grid'] == 1].copy()
    else:
        candidates = df.copy()

    candidates = candidates.sort_values('suntower_score_10', ascending=False)
    cumulative_cost = candidates['capex_usd'].cumsum()
    selected = candidates[cumulative_cost <= budget_usd].copy()

    return selected


def compute_impact(selected: pd.DataFrame) -> dict:
    """Compute aggregated impact metrics for selected towers."""
    if len(selected) == 0:
        return {
            'towers_selected': 0,
            'total_capex_usd': 0,
            'annual_savings_usd': 0,
            'annual_co2_avoided_tonnes': 0,
            'population_served': 0,
            'diesel_litres_saved_year': 0,
            'payback_years': 0,
            'avg_score': 0,
        }

    total_capex = selected['capex_usd'].sum()
    annual_savings = selected['total_savings_usd_year'].sum()

    return {
        'towers_selected': len(selected),
        'total_capex_usd': total_capex,
        'annual_savings_usd': annual_savings,
        'annual_co2_avoided_tonnes': selected['co2_avoided_tonnes_year'].sum(),
        'population_served': selected['population_5km'].sum(),
        'diesel_litres_saved_year': selected['diesel_litres_year'].sum() * 0.70,
        'payback_years': total_capex / annual_savings if annual_savings > 0 else 999,
        'avg_score': selected['suntower_score_10'].mean(),
    }


def scenario_compare(df: pd.DataFrame, budget_usd: float) -> dict:
    """Compare different priority scenarios at the same budget level."""
    results = {}
    for name, weights in SCENARIO_WEIGHTS.items():
        scored = compute_scores(df, weights)
        selected = budget_allocation(scored, budget_usd, candidates_only=False)
        impact = compute_impact(selected)
        impact['scenario'] = name
        results[name] = impact
    return results
