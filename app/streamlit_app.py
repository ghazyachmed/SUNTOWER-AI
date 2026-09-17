"""
SUNTOWER-AI — GeoAI Capital Allocation Engine for Sustainable Telecom Infrastructure
Interactive Dashboard (Streamlit + Folium)

ASEAN GeoAI Fusion 2026 Hackathon — Team HACK-ID-068
"""

import streamlit as st
import pandas as pd
import numpy as np
import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import plotly.express as px
import plotly.graph_objects as go
import json
import os
import sys

# Add scripts to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from scoring_engine import (
    compute_scores, budget_allocation, compute_impact,
    scenario_compare, SCENARIO_WEIGHTS, DEFAULT_WEIGHTS
)

# -------------------------------------------------------------------
# Page Configuration
# -------------------------------------------------------------------
st.set_page_config(
    page_title="SUNTOWER-AI | GeoAI Capital Allocation Engine",
    page_icon="☀️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# -------------------------------------------------------------------
# Custom CSS
# -------------------------------------------------------------------
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');

    * { font-family: 'Inter', sans-serif; }

    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 1rem;
        max-width: 100%;
    }

    /* Header */
    .hero-header {
        background: linear-gradient(135deg, #0f172a 0%, #1e3a5f 40%, #0c4a6e 100%);
        border-radius: 16px;
        padding: 1.8rem 2rem;
        margin-bottom: 1.2rem;
        border: 1px solid rgba(255, 191, 0, 0.15);
        position: relative;
        overflow: hidden;
    }
    .hero-header::before {
        content: '';
        position: absolute;
        top: -50%;
        right: -10%;
        width: 300px;
        height: 300px;
        background: radial-gradient(circle, rgba(251, 191, 36, 0.12) 0%, transparent 70%);
        pointer-events: none;
    }
    .hero-title {
        font-size: 1.9rem;
        font-weight: 900;
        color: #f8fafc;
        margin: 0 0 0.25rem 0;
        letter-spacing: -0.03em;
    }
    .hero-title span {
        background: linear-gradient(90deg, #fbbf24, #f59e0b);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
    }
    .hero-sub {
        font-size: 0.92rem;
        color: #94a3b8;
        margin: 0;
        font-weight: 400;
        line-height: 1.5;
    }
    .hero-tagline {
        font-size: 0.78rem;
        color: #fbbf24;
        font-weight: 700;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        margin-top: 0.5rem;
    }

    /* Metric Cards */
    .metric-card {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 14px;
        padding: 1.1rem 1.2rem;
        text-align: center;
    }
    .metric-value {
        font-size: 1.7rem;
        font-weight: 900;
        color: #f8fafc;
        letter-spacing: -0.02em;
        line-height: 1.1;
    }
    .metric-label {
        font-size: 0.68rem;
        color: #64748b;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        font-weight: 700;
        margin-top: 0.3rem;
    }
    .metric-highlight {
        border-color: rgba(251, 191, 36, 0.3);
        background: linear-gradient(135deg, #1e293b, #1a2332);
    }
    .metric-highlight .metric-value {
        color: #fbbf24;
    }

    /* Tower Detail Card */
    .tower-detail {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid rgba(148, 163, 184, 0.15);
        border-radius: 16px;
        padding: 1.5rem;
    }
    .tower-detail h3 {
        color: #f8fafc;
        font-weight: 800;
        margin-bottom: 0.5rem;
    }

    /* Info badge */
    .info-badge {
        display: inline-block;
        background: rgba(59, 130, 246, 0.12);
        color: #60a5fa;
        padding: 0.25rem 0.7rem;
        border-radius: 999px;
        font-size: 0.7rem;
        font-weight: 700;
        letter-spacing: 0.04em;
    }
    .info-badge.green {
        background: rgba(34, 197, 94, 0.12);
        color: #4ade80;
    }
    .info-badge.amber {
        background: rgba(251, 191, 36, 0.12);
        color: #fbbf24;
    }
    .info-badge.red {
        background: rgba(239, 68, 68, 0.12);
        color: #f87171;
    }

    /* Sidebar styling */
    section[data-testid="stSidebar"] {
        background: #0f172a;
    }
    section[data-testid="stSidebar"] .stMarkdown h1,
    section[data-testid="stSidebar"] .stMarkdown h2,
    section[data-testid="stSidebar"] .stMarkdown h3 {
        color: #f8fafc;
    }

    /* Divider */
    .section-divider {
        border: none;
        border-top: 1px solid rgba(148, 163, 184, 0.1);
        margin: 1rem 0;
    }

    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    header {visibility: hidden;}

    div[data-testid="stMetric"] {
        background: linear-gradient(135deg, #1e293b, #0f172a);
        border: 1px solid rgba(148, 163, 184, 0.12);
        border-radius: 12px;
        padding: 0.8rem 1rem;
    }
</style>
""", unsafe_allow_html=True)


# -------------------------------------------------------------------
# Data Loading
# -------------------------------------------------------------------
@st.cache_data
def load_data():
    """Load enriched tower data."""
    data_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'towers_enriched.csv')
    if not os.path.exists(data_path):
        st.error(f"Data file not found: {data_path}")
        st.info("Run the data pipeline first: `python scripts/data_pipeline.py`")
        st.stop()
    df = pd.read_csv(data_path)
    return df


def get_color(score, max_score=10):
    """Get color for tower marker based on score."""
    if score >= 7.5:
        return '#22c55e'  # Green - high priority
    elif score >= 5.0:
        return '#fbbf24'  # Amber - medium priority
    elif score >= 2.5:
        return '#f97316'  # Orange - lower priority
    else:
        return '#6b7280'  # Gray - low priority


def get_priority_label(score):
    if score >= 7.5:
        return "HIGH", "green"
    elif score >= 5.0:
        return "MEDIUM", "amber"
    elif score >= 2.5:
        return "LOW", "red"
    else:
        return "MINIMAL", "red"


# -------------------------------------------------------------------
# Sidebar
# -------------------------------------------------------------------
def render_sidebar(df):
    with st.sidebar:
        st.markdown("## ☀️ SUNTOWER-AI")
        st.markdown('<p style="color: #94a3b8; font-size: 0.8rem;">GeoAI Capital Allocation Engine<br>for Sustainable Telecom Infrastructure</p>', unsafe_allow_html=True)

        st.markdown("---")

        # Budget control
        st.markdown("### 💰 Investment Budget")
        budget_usd = st.slider(
            "Budget (USD)",
            min_value=100_000,
            max_value=10_000_000,
            value=2_000_000,
            step=100_000,
            format="$%d",
            help="Set the total solarisation investment budget"
        )

        st.markdown("---")

        # Priority mode
        st.markdown("### 🎯 Priority Mode")
        scenario = st.radio(
            "Optimization Objective",
            options=['balanced', 'economic', 'carbon', 'equity'],
            format_func=lambda x: {
                'balanced': '⚖️ Balanced ESG',
                'economic': '💵 Economic (ROI)',
                'carbon': '🌿 Carbon Reduction',
                'equity': '🏘️ Connectivity Equity'
            }[x],
            index=0,
            help="Change the priority weights for tower ranking"
        )

        st.markdown("---")

        # Custom weights (advanced)
        with st.expander("⚙️ Custom Weights", expanded=False):
            w1 = st.slider("☀️ Solar Potential", 0, 100,
                          int(SCENARIO_WEIGHTS[scenario]['solar_potential'] * 100))
            w2 = st.slider("💰 Energy Savings", 0, 100,
                          int(SCENARIO_WEIGHTS[scenario]['energy_savings'] * 100))
            w3 = st.slider("🌿 Carbon Avoided", 0, 100,
                          int(SCENARIO_WEIGHTS[scenario]['carbon_avoided'] * 100))
            w4 = st.slider("🏘️ Connectivity Equity", 0, 100,
                          int(SCENARIO_WEIGHTS[scenario]['connectivity_equity'] * 100))
            w5 = st.slider("🛣️ Access Feasibility", 0, 100,
                          int(SCENARIO_WEIGHTS[scenario]['access_feasibility'] * 100))

            total = w1 + w2 + w3 + w4 + w5
            if total > 0:
                custom_weights = {
                    'solar_potential': w1 / total,
                    'energy_savings': w2 / total,
                    'carbon_avoided': w3 / total,
                    'connectivity_equity': w4 / total,
                    'access_feasibility': w5 / total,
                }
            else:
                custom_weights = SCENARIO_WEIGHTS[scenario]

            use_custom = st.checkbox("Use custom weights")

        weights = custom_weights if use_custom else SCENARIO_WEIGHTS[scenario]

        st.markdown("---")

        # Filter options
        st.markdown("### 🔍 Filters")
        show_only_offgrid = st.checkbox("Show only weak-grid / off-grid", value=False)
        show_selected_only = st.checkbox("Show only budget-selected towers", value=False)

        st.markdown("---")
        st.markdown(
            '<p style="color: #475569; font-size: 0.65rem; text-align: center;">'
            'ASEAN GeoAI Fusion 2026<br>HACK-ID-068 | Team Suntower</p>',
            unsafe_allow_html=True
        )

        return budget_usd, weights, scenario, show_only_offgrid, show_selected_only


# -------------------------------------------------------------------
# Main Content
# -------------------------------------------------------------------
def render_header():
    st.markdown("""
    <div class="hero-header">
        <div class="hero-title">☀️ SUNTOWER<span>-AI</span></div>
        <p class="hero-sub">
            GeoAI Capital Allocation Engine for Sustainable Telecom Infrastructure.
            Fusing satellite-derived solar irradiance, population density, terrain, and economic data
            to optimise solarisation investment across ASEAN telecom towers.
        </p>
        <div class="hero-tagline">Not where the sun shines — where your investment shines brightest.</div>
    </div>
    """, unsafe_allow_html=True)


def render_metrics(impact, total_offgrid, total_towers):
    cols = st.columns(6)

    with cols[0]:
        st.markdown(f"""
        <div class="metric-card metric-highlight">
            <div class="metric-value">{impact['towers_selected']}</div>
            <div class="metric-label">Towers Selected</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[1]:
        savings = impact['annual_savings_usd']
        if savings >= 1_000_000:
            savings_str = f"${savings/1_000_000:.1f}M"
        else:
            savings_str = f"${savings/1_000:.0f}K"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{savings_str}</div>
            <div class="metric-label">Annual Savings</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[2]:
        co2 = impact['annual_co2_avoided_tonnes']
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{co2:,.0f}</div>
            <div class="metric-label">Tonnes CO₂/yr Avoided</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[3]:
        pop = impact['population_served']
        if pop >= 1_000_000:
            pop_str = f"{pop/1_000_000:.1f}M"
        elif pop >= 1_000:
            pop_str = f"{pop/1_000:.0f}K"
        else:
            pop_str = str(pop)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{pop_str}</div>
            <div class="metric-label">Population Served</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[4]:
        payback = impact['payback_years']
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{payback:.1f}yr</div>
            <div class="metric-label">Avg Payback Period</div>
        </div>
        """, unsafe_allow_html=True)

    with cols[5]:
        capex = impact['total_capex_usd']
        if capex >= 1_000_000:
            capex_str = f"${capex/1_000_000:.1f}M"
        else:
            capex_str = f"${capex/1_000:.0f}K"
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-value">{capex_str}</div>
            <div class="metric-label">Total CAPEX Deployed</div>
        </div>
        """, unsafe_allow_html=True)


def create_map(df_display, selected_ids, center_lat, center_lon):
    """Create the Folium map with scored towers."""
    m = folium.Map(
        location=[center_lat, center_lon],
        zoom_start=9,
        tiles=None,
        control_scale=True,
    )

    # Dark tile layer
    folium.TileLayer(
        tiles='https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png',
        attr='&copy; <a href="https://carto.com/">CARTO</a>',
        name='Dark Base',
        control=False,
    ).add_to(m)

    # Add towers
    for _, row in df_display.iterrows():
        score = row.get('suntower_score_10', 0)
        is_selected = row['id'] in selected_ids if len(selected_ids) > 0 else False
        is_offgrid = row.get('is_off_grid', 0) == 1

        color = get_color(score)
        radius = 6 if is_selected else 4
        opacity = 0.9 if is_selected else 0.5
        weight = 2 if is_selected else 0.5

        if not is_offgrid:
            color = '#374151'
            opacity = 0.25
            radius = 3

        priority_label, badge_class = get_priority_label(score)

        popup_html = f"""
        <div style="font-family: Inter, sans-serif; min-width: 260px; padding: 4px;">
            <h4 style="margin: 0 0 6px; font-size: 13px; color: #1e293b;">
                Tower #{int(row['id'])}
                <span style="float: right; font-size: 11px; background: {color};
                      color: white; padding: 2px 8px; border-radius: 10px;">{priority_label}</span>
            </h4>
            <p style="margin: 0 0 6px; font-size: 11px; color: #64748b;">
                {row.get('bps_nama_kabupaten_kota', 'N/A')} · {row.get('bps_nama_kecamatan', 'N/A')}
            </p>
            <hr style="border: none; border-top: 1px solid #e2e8f0; margin: 6px 0;">
            <table style="width: 100%; font-size: 11px; color: #334155;">
                <tr><td>☀️ <b>SUNTOWER Score</b></td><td style="text-align:right"><b>{score:.1f}/10</b></td></tr>
                <tr><td>🔆 GHI</td><td style="text-align:right">{row['ghi_kwh_m2_day']:.2f} kWh/m²/day</td></tr>
                <tr><td>👥 Population (5km)</td><td style="text-align:right">{row['population_5km']:,}</td></tr>
                <tr><td>💰 Energy Savings</td><td style="text-align:right">${row['total_savings_usd_year']:,.0f}/yr</td></tr>
                <tr><td>🌿 CO₂ Avoided</td><td style="text-align:right">{row['co2_avoided_tonnes_year']:.1f} t/yr</td></tr>
                <tr><td>🛣️ Road Distance</td><td style="text-align:right">{row['road_distance_km']:.1f} km</td></tr>
                <tr><td>🔌 Grid Status</td><td style="text-align:right">{row.get('grid_status_label', 'Off-Grid' if is_offgrid else 'Grid')}</td></tr>
                <tr><td>📡 Owner</td><td style="text-align:right">{row.get('pemilik_menara', 'N/A')[:20]}</td></tr>
                <tr><td>🏗️ Height</td><td style="text-align:right">{row.get('tower_height', 'N/A')}m</td></tr>
            </table>
        </div>
        """

        folium.CircleMarker(
            location=[row['lat'], row['long']],
            radius=radius,
            color=color,
            fill=True,
            fillColor=color,
            fillOpacity=opacity,
            weight=weight,
            popup=folium.Popup(popup_html, max_width=320),
        ).add_to(m)

    # Legend
    legend_html = """
    <div style="position: fixed; bottom: 30px; left: 50px; z-index: 9999;
         background: rgba(15, 23, 42, 0.92); padding: 14px 18px;
         border-radius: 12px; border: 1px solid rgba(148, 163, 184, 0.2);
         font-family: Inter, sans-serif; backdrop-filter: blur(8px);">
        <div style="font-size: 11px; font-weight: 800; color: #f8fafc; margin-bottom: 8px;
                    letter-spacing: 0.06em; text-transform: uppercase;">
            SUNTOWER Priority
        </div>
        <div style="font-size: 11px; color: #94a3b8; line-height: 1.8;">
            <span style="color: #22c55e;">●</span> High (7.5+) &nbsp;
            <span style="color: #fbbf24;">●</span> Medium (5.0-7.5) &nbsp;
            <span style="color: #f97316;">●</span> Low (2.5-5.0) &nbsp;
            <span style="color: #6b7280;">●</span> Minimal / Grid
        </div>
    </div>
    """
    m.get_root().html.add_child(folium.Element(legend_html))

    return m


def render_scenario_comparison(df, budget_usd):
    """Render scenario comparison charts."""
    st.markdown("### 📊 Scenario Comparison")
    st.caption("Same budget, different priorities — see how allocation changes")

    comparisons = scenario_compare(df, budget_usd)

    # Build comparison dataframe
    comp_rows = []
    for name, impact in comparisons.items():
        comp_rows.append({
            'Scenario': name.title(),
            'Towers': impact['towers_selected'],
            'Savings ($/yr)': impact['annual_savings_usd'],
            'CO₂ Avoided (t/yr)': impact['annual_co2_avoided_tonnes'],
            'Population': impact['population_served'],
            'Payback (yr)': impact['payback_years'],
        })
    comp_df = pd.DataFrame(comp_rows)

    cols = st.columns(2)

    with cols[0]:
        fig = go.Figure()
        fig.add_trace(go.Bar(
            x=comp_df['Scenario'],
            y=comp_df['CO₂ Avoided (t/yr)'],
            name='CO₂ Avoided',
            marker_color=['#3b82f6', '#22c55e', '#22c55e', '#3b82f6'],
            text=comp_df['CO₂ Avoided (t/yr)'].apply(lambda x: f'{x:,.0f}t'),
            textposition='outside',
        ))
        fig.update_layout(
            title=dict(text='CO₂ Avoided per Scenario', font=dict(size=14)),
            yaxis_title='Tonnes CO₂/year',
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=300,
            margin=dict(t=40, b=20, l=40, r=20),
        )
        st.plotly_chart(fig, width="stretch")

    with cols[1]:
        fig2 = go.Figure()
        fig2.add_trace(go.Bar(
            x=comp_df['Scenario'],
            y=comp_df['Population'],
            name='Population Served',
            marker_color=['#3b82f6', '#3b82f6', '#3b82f6', '#fbbf24'],
            text=comp_df['Population'].apply(lambda x: f'{x/1000:.0f}K'),
            textposition='outside',
        ))
        fig2.update_layout(
            title=dict(text='Population Served per Scenario', font=dict(size=14)),
            yaxis_title='People',
            template='plotly_dark',
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            height=300,
            margin=dict(t=40, b=20, l=40, r=20),
        )
        st.plotly_chart(fig2, width="stretch")


def render_cumulative_impact(selected_df):
    """Render cumulative impact curve."""
    if len(selected_df) == 0:
        return

    sorted_sel = selected_df.sort_values('suntower_score_10', ascending=False)
    sorted_sel['cum_capex'] = sorted_sel['capex_usd'].cumsum()
    sorted_sel['cum_co2'] = sorted_sel['co2_avoided_tonnes_year'].cumsum()
    sorted_sel['cum_savings'] = sorted_sel['total_savings_usd_year'].cumsum()
    sorted_sel['tower_num'] = range(1, len(sorted_sel) + 1)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_sel['cum_capex'],
        y=sorted_sel['cum_co2'],
        mode='lines+markers',
        name='CO₂ Avoided',
        line=dict(color='#22c55e', width=2),
        marker=dict(size=4),
        hovertemplate='CAPEX: $%{x:,.0f}<br>CO₂ Avoided: %{y:.0f} t/yr<extra></extra>'
    ))
    fig.update_layout(
        title=dict(text='Cumulative Impact vs Investment', font=dict(size=14)),
        xaxis_title='Cumulative CAPEX (USD)',
        yaxis_title='Cumulative CO₂ Avoided (tonnes/yr)',
        template='plotly_dark',
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        height=300,
        margin=dict(t=40, b=40, l=50, r=20),
    )
    st.plotly_chart(fig, width="stretch")


def render_tower_table(selected_df):
    """Render top towers table."""
    if len(selected_df) == 0:
        st.info("No towers selected within current budget. Increase budget or adjust filters.")
        return

    display_cols = {
        'rank': 'Rank',
        'id': 'Tower ID',
        'bps_nama_kabupaten_kota': 'District',
        'suntower_score_10': 'Score',
        'ghi_kwh_m2_day': 'GHI',
        'population_5km': 'Population (5km)',
        'total_savings_usd_year': 'Savings ($/yr)',
        'co2_avoided_tonnes_year': 'CO₂ Avoided (t/yr)',
        'road_distance_km': 'Road Dist (km)',
        'pemilik_menara': 'Owner',
    }

    top = selected_df.sort_values('suntower_score_10', ascending=False).head(20)
    display = top[[c for c in display_cols.keys() if c in top.columns]].copy()
    display = display.rename(columns=display_cols)

    st.dataframe(
        display,
        width="stretch",
        hide_index=True,
        column_config={
            'Score': st.column_config.ProgressColumn(
                format="%.1f",
                min_value=0,
                max_value=10,
            ),
            'GHI': st.column_config.NumberColumn(format="%.2f"),
            'Population (5km)': st.column_config.NumberColumn(format="%d"),
            'Savings ($/yr)': st.column_config.NumberColumn(format="$%.0f"),
            'CO₂ Avoided (t/yr)': st.column_config.NumberColumn(format="%.1f"),
            'Road Dist (km)': st.column_config.NumberColumn(format="%.1f"),
        }
    )


# -------------------------------------------------------------------
# Main App
# -------------------------------------------------------------------
def main():
    # Load data
    df = load_data()

    # Render sidebar
    budget_usd, weights, scenario, show_only_offgrid, show_selected_only = render_sidebar(df)

    # Compute scores
    scored_df = compute_scores(df, weights)

    # Budget allocation
    selected = budget_allocation(scored_df, budget_usd, candidates_only=False)
    impact = compute_impact(selected)
    selected_ids = set(selected['id'].tolist()) if len(selected) > 0 else set()

    # Header
    render_header()

    # Metrics row
    total_offgrid = scored_df[scored_df['is_off_grid'] == 1].shape[0]
    render_metrics(impact, total_offgrid, len(scored_df))

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Main content area
    map_col, detail_col = st.columns([3, 1])

    with map_col:
        st.markdown("### 🗺️ Tower Priority Map")

        # Filter data for display
        if show_selected_only:
            df_display = scored_df[scored_df['id'].isin(selected_ids)]
        elif show_only_offgrid:
            df_display = scored_df[scored_df['is_off_grid'] == 1]
        else:
            df_display = scored_df

        if len(df_display) > 0:
            center_lat = df_display['lat'].mean()
            center_lon = df_display['long'].mean()
        else:
            center_lat, center_lon = -6.9, 107.6

        m = create_map(df_display, selected_ids, center_lat, center_lon)
        st_folium(m, height=520, use_container_width=True, returned_objects=[])

    with detail_col:
        st.markdown("### 📋 Quick Stats")

        st.markdown(f"""
        <div class="tower-detail">
            <p style="color: #94a3b8; font-size: 0.75rem; margin: 0 0 8px;">Analysis Summary</p>
            <table style="width: 100%; font-size: 0.8rem; color: #cbd5e1;">
                <tr><td>Total Towers</td><td style="text-align: right; font-weight: 700;">{len(scored_df):,}</td></tr>
                <tr><td>Off-Grid Towers</td><td style="text-align: right; font-weight: 700;">{total_offgrid}</td></tr>
                <tr><td>Budget Allocated</td><td style="text-align: right; font-weight: 700;">${budget_usd:,.0f}</td></tr>
                <tr><td>Towers Selected</td><td style="text-align: right; font-weight: 700; color: #fbbf24;">{impact['towers_selected']}</td></tr>
                <tr><td>Priority Mode</td><td style="text-align: right; font-weight: 700;">{scenario.title()}</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")

        # Weight visualization
        st.markdown(f"""
        <div class="tower-detail" style="margin-top: 8px;">
            <p style="color: #94a3b8; font-size: 0.75rem; margin: 0 0 8px;">Current Weights</p>
            <table style="width: 100%; font-size: 0.75rem; color: #cbd5e1;">
                <tr><td>☀️ Solar</td><td style="text-align: right;">{weights['solar_potential']*100:.0f}%</td></tr>
                <tr><td>💰 Savings</td><td style="text-align: right;">{weights['energy_savings']*100:.0f}%</td></tr>
                <tr><td>🌿 Carbon</td><td style="text-align: right;">{weights['carbon_avoided']*100:.0f}%</td></tr>
                <tr><td>🏘️ Equity</td><td style="text-align: right;">{weights['connectivity_equity']*100:.0f}%</td></tr>
                <tr><td>🛣️ Access</td><td style="text-align: right;">{weights['access_feasibility']*100:.0f}%</td></tr>
            </table>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("")

        # Methodology
        with st.expander("ℹ️ Methodology"):
            st.markdown("""
            **SUNTOWER-AI** fuses 8 open geospatial datasets:
            - 🔆 Solar irradiance (Global Solar Atlas model)
            - 👥 Population density (WorldPop proxy)
            - 🏔️ Terrain (SRTM elevation model)
            - 🌙 Nighttime lights (VIIRS off-grid proxy)
            - 🛣️ Road network (OSM distance)
            - 🌍 Land cover (ESA WorldCover)
            - ⛽ Diesel prices (public databases)
            - 📡 Tower data (AGAIF + OpenCelliD)

            **Scoring**: Multi-criteria weighted analysis
            with user-configurable ESG priorities.

            **Budget Allocation**: Greedy ranking
            with capital constraint optimization.
            """)

    st.markdown('<hr class="section-divider">', unsafe_allow_html=True)

    # Bottom section: Charts + Table
    tab1, tab2, tab3 = st.tabs(["📊 Scenario Comparison", "📈 Impact Curve", "📋 Priority Table"])

    with tab1:
        render_scenario_comparison(df, budget_usd)

    with tab2:
        render_cumulative_impact(selected)

    with tab3:
        st.markdown("### Top Priority Towers")
        render_tower_table(selected)

        # Download button
        if len(selected) > 0:
            csv_data = selected.to_csv(index=False)
            st.download_button(
                label="📥 Download Priority List (CSV)",
                data=csv_data,
                file_name="suntower_priority_list.csv",
                mime="text/csv",
            )


if __name__ == "__main__":
    main()
