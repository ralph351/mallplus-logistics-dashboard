"""
MallPlus Logistics Dashboard v4.2 - Metric Cards with Trend Lines
Real-time KPI monitoring with 5 sections: Network, Cost, Operations, SLA Breach, Lost & Damaged
Each section displays metric cards with daily trend charts
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
import requests
from io import StringIO

# ============================================================================
# PAGE CONFIG & STYLING
# ============================================================================

st.set_page_config(
    page_title="MallPlus Logistics Dashboard",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    .metric-container {
        background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
    }
    .metric-value {
        font-size: 36px;
        font-weight: bold;
        color: #f1f5f9;
        margin: 10px 0;
    }
    .metric-label {
        font-size: 12px;
        color: #94a3b8;
        font-weight: 500;
    }
    .metric-delta {
        font-size: 13px;
        margin-top: 8px;
    }
    .delta-positive {
        color: #10b981;
    }
    .delta-negative {
        color: #ef4444;
    }
    .section-title {
        font-size: 20px;
        font-weight: bold;
        margin-top: 30px;
        margin-bottom: 20px;
        color: #f1f5f9;
        border-left: 4px solid #667eea;
        padding-left: 12px;
    }
</style>
""", unsafe_allow_html=True)

st.title("🚚 MallPlus Logistics Dashboard")
st.markdown("**Real-time KPI Monitoring with Daily Trends** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8"))

# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=300)
def load_data():
    """Load corrected mock data from Google Sheets."""
    try:
        sheet_id = "1zTGMztXvfsl4oIt1X6whtW2hC4tJgKOnYtXHt6NrncY"
        gid = "0"
        csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"
        
        response = requests.get(csv_url, timeout=10)
        response.raise_for_status()
        df = pd.read_csv(StringIO(response.text))
        df = df.loc[:, ~df.columns.duplicated(keep='first')]
        
        return df
    except Exception as e:
        st.error(f"❌ Failed to load data: {str(e)}")
        return pd.DataFrame()

def prepare_data(df):
    """Convert types and clean data."""
    if df.empty:
        return df
    
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    
    timestamp_cols = [
        'order_create_ts', 'lvl1_READY_FOR_HANDOVER_ts', 'lvl1_IN_TRANSIT_ts',
        'ship_by_date_ts', 'target_pickup_date', 'forward_delivery_date_based_on_sla',
        'forward_journey_closure_soft_breach_date', 'forward_journey_closure_hard_breach_date',
        'rts_journey_closure_soft_breach_date', 'rts_journey_closure_hard_breach_date',
        'lvl2_domestic_delivered_ts', 'lvl2_domestic_pickup_sign_in_success_ts'
    ]
    
    for col in timestamp_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    numeric_cols = [
        'system_chargeable_weight', 'actual_chargeable_weight', 
        'estimated_shipping_fee', 'actual_shipping_fee',
        'ship_by_date_sla', 'target_pickup_date_sla',
        'forward_delivery_sla', 'forward_journey_closure_soft_breach_sla',
        'forward_journey_closure_hard_breach_sla', 'rts_journey_closure_sla',
        'rts_journey_closure_soft_breach_sla', 'rts_journey_closure_hard_breach_sla',
        'package_value'
    ]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    flag_cols = ['is_forward_soft_breach', 'is_forward_hard_breach', 'is_rts_soft_breach', 'is_rts_hard_breach']
    for col in flag_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    return df

# Load data
df = load_data()
df = prepare_data(df)

if df.empty:
    st.error("❌ No data loaded.")
    st.stop()

# ============================================================================
# TIME FILTERS (SIDEBAR)
# ============================================================================

st.sidebar.markdown("### 📅 Time Filters")

min_date = df['order_create_ts'].min().date() if pd.notna(df['order_create_ts'].min()) else datetime.now().date()
max_date = df['order_create_ts'].max().date() if pd.notna(df['order_create_ts'].max()) else datetime.now().date()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    df = df[(df['order_create_ts'].dt.date >= start_date) & (df['order_create_ts'].dt.date <= end_date)]

# Region filter
st.sidebar.markdown("### 🗺️ Region")
regions = ["All"] + sorted(df['origin_region'].dropna().unique().tolist())
selected_region = st.sidebar.selectbox("Origin Region", regions)

if selected_region != "All":
    df = df[df['origin_region'] == selected_region]

# 3PL filter
st.sidebar.markdown("### 🏢 3PL")
three_pls = ["All"] + sorted(df['fm_3pl_name'].dropna().unique().tolist())
selected_3pl = st.sidebar.selectbox("First-Mile 3PL", three_pls)

if selected_3pl != "All":
    df = df[df['fm_3pl_name'] == selected_3pl]

st.sidebar.markdown(f"**Records:** {len(df):,}")

# ============================================================================
# HELPER: Build trend chart (line with target dashed line)
# ============================================================================

def create_trend_chart(data, x_col, y_col, title, target_value=None, color='#667eea'):
    """Create a line chart with optional target threshold."""
    
    daily = data.groupby(pd.Grouper(key=x_col, freq='D'))[y_col].agg(['mean', 'count']).reset_index()
    daily = daily[daily['count'] > 0]  # Remove empty days
    
    if daily.empty:
        return go.Figure().add_annotation(text="No data", xref="paper", yref="paper")
    
    fig = go.Figure()
    
    # Main trend line
    fig.add_trace(go.Scatter(
        x=daily[x_col],
        y=daily['mean'],
        mode='lines+markers',
        name='Trend',
        line=dict(color=color, width=2),
        marker=dict(size=6),
        hovertemplate='<b>%{x|%b %d}</b><br>%{y:.1f}<extra></extra>'
    ))
    
    # Target line (red dashed)
    if target_value:
        fig.add_hline(
            y=target_value,
            line_dash="dash",
            line_color="#ef4444",
            annotation_text="Target",
            annotation_position="right"
        )
    
    fig.update_layout(
        title=title,
        xaxis_title="Date",
        yaxis_title="Value",
        hovermode='x unified',
        height=300,
        template='plotly_dark',
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=40)
    )
    
    return fig

# ============================================================================
# KPI CALCULATIONS (Daily aggregations)
# ============================================================================

def daily_kpis(df):
    """Calculate daily KPI trends."""
    daily = df.groupby(df['order_create_ts'].dt.date).agg({
        'tracking_number': 'count',
        'pickup_sla_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'actual_shipping_fee': 'mean',
        'is_forward_soft_breach': 'sum',
        'is_forward_hard_breach': 'sum',
    }).reset_index()
    
    daily.columns = ['date', 'parcel_count', 'pickup_sla_pct', 'forward_sla_pct', 'avg_fee', 'soft_breaches', 'hard_breaches']
    daily['date'] = pd.to_datetime(daily['date'])
    
    return daily

daily = daily_kpis(df)

# ============================================================================
# SECTION 1: COST
# ============================================================================

st.markdown('<div class="section-title">💰 Cost Performance</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Current CPP
    current_cpp = df['actual_shipping_fee'].mean()
    prev_cpp = df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]['actual_shipping_fee'].mean()
    delta_cpp = current_cpp - prev_cpp
    delta_pct = (delta_cpp / prev_cpp * 100) if prev_cpp > 0 else 0
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Cost Per Parcel (₱)</div>
        <div class="metric-value">₱{current_cpp:.2f}</div>
        <div class="metric-delta {'delta-negative' if delta_cpp > 0 else 'delta-positive'}">
            {'↑' if delta_cpp > 0 else '↓'} ₱{abs(delta_cpp):.2f} vs ₱{prev_cpp:.2f}
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # CPP Trend
    daily_copy = daily.copy()
    daily_copy['date_str'] = daily_copy['date'].dt.strftime('%Y-%m-%d')
    fig_cpp = create_trend_chart(
        daily_copy.assign(order_create_ts=daily_copy['date']),
        'order_create_ts',
        'avg_fee',
        'CPP Trend',
        target_value=81.04,
        color='#667eea'
    )
    st.plotly_chart(fig_cpp, use_container_width=True)

# ============================================================================
# SECTION 2: OPERATIONS
# ============================================================================

st.markdown('<div class="section-title">⚙️ Operations</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Forward Delivery Compliance
    fwd_comp = (df['forward_delivery_compliance'] == 'pass').sum() / len(df) * 100
    fwd_prev = (df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]['forward_delivery_compliance'] == 'pass').sum() / max(len(df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]), 1) * 100
    delta_fwd = fwd_comp - fwd_prev
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">3b. Forward Delivery Compliance %</div>
        <div class="metric-value">{fwd_comp:.1f}%</div>
        <div class="metric-delta {'delta-positive' if delta_fwd > 0 else 'delta-negative'}">
            {'↑' if delta_fwd > 0 else '↓'} {abs(delta_fwd):.1f}% vs {fwd_prev:.1f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # Forward Delivery Compliance Trend
    daily_copy = daily.copy()
    daily_copy['date_str'] = daily_copy['date'].dt.strftime('%Y-%m-%d')
    fig_fwd = create_trend_chart(
        daily_copy.assign(order_create_ts=daily_copy['date']),
        'order_create_ts',
        'forward_sla_pct',
        'Forward Delivery Compliance Trend',
        target_value=90,
        color='#10b981'
    )
    st.plotly_chart(fig_fwd, use_container_width=True)

# ============================================================================
# SECTION 3: NETWORK
# ============================================================================

st.markdown('<div class="section-title">🌐 Network Performance</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Pickup SLA Compliance
    pickup_comp = (df['pickup_sla_compliance'] == 'pass').sum() / len(df) * 100
    pickup_prev = (df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]['pickup_sla_compliance'] == 'pass').sum() / max(len(df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]), 1) * 100
    delta_pickup = pickup_comp - pickup_prev
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Pickup SLA Compliance %</div>
        <div class="metric-value">{pickup_comp:.1f}%</div>
        <div class="metric-delta {'delta-positive' if delta_pickup > 0 else 'delta-negative'}">
            {'↑' if delta_pickup > 0 else '↓'} {abs(delta_pickup):.1f}% vs {pickup_prev:.1f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # Pickup SLA Trend
    daily_copy = daily.copy()
    daily_copy['date_str'] = daily_copy['date'].dt.strftime('%Y-%m-%d')
    fig_pickup = create_trend_chart(
        daily_copy.assign(order_create_ts=daily_copy['date']),
        'order_create_ts',
        'pickup_sla_pct',
        'Pickup SLA Compliance Trend',
        target_value=95,
        color='#3b82f6'
    )
    st.plotly_chart(fig_pickup, use_container_width=True)

# ============================================================================
# SECTION 4: SLA BREACH
# ============================================================================

st.markdown('<div class="section-title">⚠️ SLA Breach Analysis</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Soft Breaches
    soft_count = df['is_forward_soft_breach'].sum()
    soft_pct = soft_count / len(df) * 100
    soft_prev = df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]['is_forward_soft_breach'].sum()
    soft_prev_pct = soft_prev / max(len(df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]), 1) * 100
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Forward Soft Breaches</div>
        <div class="metric-value">{soft_count:.0f} ({soft_pct:.1f}%)</div>
        <div class="metric-delta {'delta-negative' if soft_count > soft_prev else 'delta-positive'}">
            {'↑' if soft_count > soft_prev else '↓'} {soft_count - soft_prev:.0f} vs {soft_prev_pct:.1f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # Soft Breach Trend
    daily_copy = daily.copy()
    daily_copy['date_str'] = daily_copy['date'].dt.strftime('%Y-%m-%d')
    fig_soft = create_trend_chart(
        daily_copy.assign(order_create_ts=daily_copy['date']),
        'order_create_ts',
        'soft_breaches',
        'Soft Breach Trend',
        target_value=None,
        color='#f59e0b'
    )
    st.plotly_chart(fig_soft, use_container_width=True)

# ============================================================================
# SECTION 5: LOST & DAMAGED
# ============================================================================

st.markdown('<div class="section-title">📦 Lost & Damaged Packages</div>', unsafe_allow_html=True)

col1, col2 = st.columns(2)

with col1:
    # Package Loss Rate
    lost_count = len(df[df['final_status'] == 'PACKAGE_LOST'])
    loss_rate = lost_count / len(df) * 100
    
    lost_prev = len(df[(df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)) & (df['final_status'] == 'PACKAGE_LOST')])
    loss_prev_rate = lost_prev / max(len(df[df['order_create_ts'] < df['order_create_ts'].max() - timedelta(days=1)]), 1) * 100
    
    st.markdown(f"""
    <div class="metric-container">
        <div class="metric-label">Package Loss Rate</div>
        <div class="metric-value">{loss_rate:.2f}%</div>
        <div class="metric-delta {'delta-negative' if loss_rate > loss_prev_rate else 'delta-positive'}">
            {lost_count} lost packages | Prev: {loss_prev_rate:.2f}%
        </div>
    </div>
    """, unsafe_allow_html=True)

with col2:
    # Loss Trend
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%); padding: 20px; border-radius: 12px; border: 1px solid #334155;">
        <div style="font-size: 12px; color: #94a3b8; margin-bottom: 10px;">Top Loss Reasons</div>
        <div style="font-size: 14px; color: #f1f5f9;">
    """, unsafe_allow_html=True)
    
    loss_reasons = df[df['final_status'] == 'PACKAGE_LOST']['package_lost_reason'].value_counts().head(5)
    for reason, count in loss_reasons.items():
        st.markdown(f"**{reason}**: {count} cases", unsafe_allow_html=True)
    
    st.markdown("</div></div>", unsafe_allow_html=True)

# ============================================================================
# DEBUG
# ============================================================================

with st.expander("🔧 Debug"):
    st.write(f"Records: {len(df):,} | Columns: {len(df.columns)}")
