"""
MallPlus Logistics Dashboard v4.2 - Full Redesign with 5 KPI Sections
Real-time logistics KPI monitoring with cost, performance, SLA, and anomaly detection
144-field schema with corrected SLA calculations
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
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="MallPlus Logistics Dashboard",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚚 MallPlus Logistics Dashboard v4.2")
st.markdown("**Real-time Logistics KPI Monitoring** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8") + " | Status: ✅ Synced")

# ============================================================================
# DATA LOADING - Direct CSV from Google Sheets
# ============================================================================

@st.cache_data(ttl=300)
def load_data():
    """Load corrected mock data from Google Sheets (144 columns, SLA fields corrected)."""
    try:
        # Corrected sheet: 144 columns with proper SLA types
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

# ============================================================================
# DATA PREP
# ============================================================================

def prepare_data(df):
    """Convert types and clean data."""
    if df.empty:
        return df
    
    df = df.loc[:, ~df.columns.duplicated(keep='first')]
    
    # Timestamp columns
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
    
    # Numeric columns
    numeric_cols = [
        'system_chargeable_weight', 'actual_chargeable_weight', 
        'estimated_shipping_fee', 'actual_shipping_fee',
        'ship_by_date_sla', 'target_pickup_date_sla',
        'forward_delivery_sla', 'forward_journey_closure_soft_breach_sla',
        'forward_journey_closure_hard_breach_sla', 'rts_journey_closure_sla',
        'rts_journey_closure_soft_breach_sla', 'rts_journey_closure_hard_breach_sla'
    ]
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Breach flags (1/0)
    flag_cols = ['is_forward_soft_breach', 'is_forward_hard_breach', 'is_rts_soft_breach', 'is_rts_hard_breach']
    for col in flag_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    return df

# ============================================================================
# LOAD & PREPARE DATA
# ============================================================================

df = load_data()
df = prepare_data(df)

if df.empty:
    st.error("❌ No data loaded. Check connection and sheet access.")
    st.stop()

# ============================================================================
# TIME FILTERS (Sidebar)
# ============================================================================

st.sidebar.markdown("### 📅 Time Filters")

# Date range filter
min_date = df['order_create_ts'].min()
max_date = df['order_create_ts'].max()

date_range = st.sidebar.date_input(
    "Select Date Range",
    value=(min_date, max_date),
    min_value=min_date,
    max_value=max_date
)

if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    df_filtered = df[(df['order_create_ts'].dt.date >= start_date) & (df['order_create_ts'].dt.date <= end_date)]
else:
    df_filtered = df

# Quick time filters
st.sidebar.markdown("### ⏱️ Quick Filters")
quick_filter = st.sidebar.radio("Select Period", ["All Data", "Last 7 Days", "Last 24 Hours"])

if quick_filter == "Last 24 Hours":
    cutoff = max_date - timedelta(days=1)
    df_filtered = df_filtered[df_filtered['order_create_ts'] >= cutoff]
elif quick_filter == "Last 7 Days":
    cutoff = max_date - timedelta(days=7)
    df_filtered = df_filtered[df_filtered['order_create_ts'] >= cutoff]

# Region filter
st.sidebar.markdown("### 🗺️ Region Filter")
regions = ["All"] + sorted(df['origin_region'].dropna().unique().tolist())
selected_region = st.sidebar.selectbox("Origin Region", regions)

if selected_region != "All":
    df_filtered = df_filtered[df_filtered['origin_region'] == selected_region]

# 3PL filter
st.sidebar.markdown("### 🏢 3PL Filter")
three_pls = ["All"] + sorted(df['fm_3pl_name'].dropna().unique().tolist())
selected_3pl = st.sidebar.selectbox("First-Mile 3PL", three_pls)

if selected_3pl != "All":
    df_filtered = df_filtered[df_filtered['fm_3pl_name'] == selected_3pl]

st.sidebar.markdown(f"**Records Shown:** {len(df_filtered)} / {len(df)}")

# ============================================================================
# KPI SECTION 1: SUMMARY CARDS
# ============================================================================

st.markdown("## 📊 Summary KPIs")

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    total_parcels = len(df_filtered)
    st.metric("Total Parcels", f"{total_parcels:,}")

with col2:
    pickup_pass = len(df_filtered[df_filtered['pickup_sla_compliance'] == 'pass'])
    pickup_pct = (pickup_pass / total_parcels * 100) if total_parcels > 0 else 0
    st.metric("Pickup Compliance", f"{pickup_pct:.1f}%", delta=f"{pickup_pass} passed")

with col3:
    forward_pass = len(df_filtered[df_filtered['forward_delivery_compliance'] == 'pass'])
    forward_pct = (forward_pass / total_parcels * 100) if total_parcels > 0 else 0
    st.metric("Forward SLA", f"{forward_pct:.1f}%", delta=f"{forward_pass} passed")

with col4:
    avg_cpp = df_filtered['actual_shipping_fee'].sum() / max(len(df_filtered), 1)
    st.metric("Avg Shipping Fee", f"₱{avg_cpp:.2f}")

with col5:
    soft_breaches = len(df_filtered[df_filtered['is_forward_soft_breach'] == 1])
    st.metric("Soft Breaches", f"{soft_breaches}")

with col6:
    hard_breaches = len(df_filtered[df_filtered['is_forward_hard_breach'] == 1])
    st.metric("Hard Breaches", f"{hard_breaches}")

# ============================================================================
# KPI SECTION 2: NETWORK PERFORMANCE
# ============================================================================

st.markdown("---")
st.markdown("## 🌐 Network Performance")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Pickup SLA Compliance by Region")
    region_pickup = df_filtered.groupby('origin_region').apply(
        lambda x: len(x[x['pickup_sla_compliance'] == 'pass']) / max(len(x), 1) * 100
    ).sort_values(ascending=False)
    
    fig = px.bar(
        x=region_pickup.index,
        y=region_pickup.values,
        labels={'x': 'Region', 'y': 'Compliance %'},
        color=region_pickup.values,
        color_continuous_scale=['#ef4444', '#fbbf24', '#10b981']
    )
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Forward Delivery SLA by 3PL")
    three_pl_forward = df_filtered.groupby('fm_3pl_name').apply(
        lambda x: len(x[x['forward_delivery_compliance'] == 'pass']) / max(len(x), 1) * 100
    ).sort_values(ascending=False)
    
    fig = px.bar(
        x=three_pl_forward.index,
        y=three_pl_forward.values,
        labels={'x': '3PL', 'y': 'Compliance %'},
        color=three_pl_forward.values,
        color_continuous_scale=['#ef4444', '#fbbf24', '#10b981']
    )
    fig.update_layout(showlegend=False, height=400)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# KPI SECTION 3: COST ANALYSIS
# ============================================================================

st.markdown("---")
st.markdown("## 💰 Cost Analysis")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Shipping Fee Distribution")
    fig = px.histogram(
        df_filtered,
        x='actual_shipping_fee',
        nbins=30,
        labels={'actual_shipping_fee': 'Shipping Fee (₱)'},
        color_discrete_sequence=['#667eea']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Cost per 3PL")
    three_pl_cost = df_filtered.groupby('fm_3pl_name')['actual_shipping_fee'].agg(['mean', 'sum', 'count'])
    
    fig = px.bar(
        three_pl_cost.reset_index(),
        x='fm_3pl_name',
        y='mean',
        labels={'fm_3pl_name': '3PL', 'mean': 'Avg Shipping Fee (₱)'},
        color='mean',
        color_continuous_scale=['#667eea', '#764ba2']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# KPI SECTION 4: OPERATIONS STATUS
# ============================================================================

st.markdown("---")
st.markdown("## ⚙️ Operations Status")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Delivery Status Distribution")
    
    # Count deliveries by final status
    status_counts = df_filtered['final_status'].value_counts().head(8)
    colors = ['#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#3b82f6', '#06b6d4', '#84cc16']
    
    fig = px.pie(
        names=status_counts.index,
        values=status_counts.values,
        color_discrete_sequence=colors
    )
    fig.update_layout(height=400)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Failed Delivery Reasons (Top 10)")
    
    # Reason codes from failed deliveries
    reason_counts = df_filtered['final_failed_delivery_reason'].value_counts().head(10)
    
    fig = px.barh(
        x=reason_counts.values,
        y=reason_counts.index,
        labels={'x': 'Count', 'y': 'Reason Code'},
        color=reason_counts.values,
        color_continuous_scale=['#667eea', '#764ba2']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# KPI SECTION 5: SLA BREACH ANALYSIS
# ============================================================================

st.markdown("---")
st.markdown("## ⚠️ SLA Breach Analysis")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Soft Breach Distribution")
    soft_by_region = df_filtered.groupby('origin_region')['is_forward_soft_breach'].sum()
    
    fig = px.bar(
        x=soft_by_region.index,
        y=soft_by_region.values,
        labels={'x': 'Region', 'y': 'Soft Breaches'},
        color=soft_by_region.values,
        color_continuous_scale=['#fbbf24', '#f59e0b']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Hard Breach Distribution")
    hard_by_region = df_filtered.groupby('origin_region')['is_forward_hard_breach'].sum()
    
    fig = px.bar(
        x=hard_by_region.index,
        y=hard_by_region.values,
        labels={'x': 'Region', 'y': 'Hard Breaches'},
        color=hard_by_region.values,
        color_continuous_scale=['#ef4444', '#dc2626']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# KPI SECTION 6: LOST & DAMAGED ANALYSIS
# ============================================================================

st.markdown("---")
st.markdown("## 📦 Lost & Damaged Packages")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Package Loss Rate by Region")
    
    lost_data = df_filtered[df_filtered['final_status'] == 'PACKAGE_LOST'].groupby('origin_region').size()
    total_by_region = df_filtered.groupby('origin_region').size()
    loss_rate = (lost_data / total_by_region * 100).fillna(0).sort_values(ascending=False)
    
    fig = px.bar(
        x=loss_rate.index,
        y=loss_rate.values,
        labels={'x': 'Region', 'y': 'Loss Rate (%)'},
        color=loss_rate.values,
        color_continuous_scale=['#10b981', '#fbbf24', '#ef4444']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Loss Reasons")
    loss_reasons = df_filtered[df_filtered['final_status'] == 'PACKAGE_LOST']['package_lost_reason'].value_counts().head(10)
    
    fig = px.barh(
        x=loss_reasons.values,
        y=loss_reasons.index,
        labels={'x': 'Count', 'y': 'Reason Code'},
        color=loss_reasons.values,
        color_continuous_scale=['#667eea', '#764ba2']
    )
    fig.update_layout(height=400, showlegend=False)
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# DEBUG INFO (Collapsible)
# ============================================================================

with st.expander("🔧 Debug Info"):
    st.write(f"**Data Shape:** {df.shape}")
    st.write(f"**Filtered Shape:** {df_filtered.shape}")
    st.write(f"**Columns:** {list(df.columns)[:20]}... ({len(df.columns)} total)")
    st.write(f"**Date Range:** {min_date} to {max_date}")
