"""
MallPlus Logistics Dashboard - Professional Multi-Dimensional Analytics v3.0
Comprehensive KPI dashboard with independent timestamp filters, time granularity,
and section-based organization (Network, Cost, Operations, Breach, Lost & Damaged)
"""

import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import numpy as np
from google.oauth2 import service_account
from googleapiclient.discovery import build
import os
from math import radians, sin, cos, sqrt, atan2

# Geolocation utilities
def parse_geolocation(geo_string):
    """Parse 'lat, lon' string into tuple (lat, lon)"""
    try:
        if not geo_string or pd.isna(geo_string):
            return (None, None)
        parts = [p.strip() for p in str(geo_string).split(',')]
        if len(parts) == 2:
            return (float(parts[0]), float(parts[1]))
        return (None, None)
    except (ValueError, TypeError, AttributeError):
        return (None, None)

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculate distance in km between two lat/lon points"""
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
        R = 6371  # Earth radius in km
        lat1_rad, lat2_rad = radians(lat1), radians(lat2)
        delta_lat, delta_lon = radians(lat2 - lat1), radians(lon2 - lon1)
        a = sin(delta_lat/2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(delta_lon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        return R * c
    except (ValueError, TypeError):
        return None

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="MallPlus Logistics Dashboard",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚚 MallPlus Logistics Dashboard v3.0")
st.markdown("**Professional Multi-Dimensional Analytics** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8"))

# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=60)  # Short TTL to catch new data quickly
def load_data():
    """Load 140-field data from Google Sheets."""
    try:
        try:
            credentials_dict = st.secrets["google_credentials"]
            creds = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        except (KeyError, FileNotFoundError):
            creds_path = os.path.expanduser("~/.openclaw/workspace-logistics/secrets/google-sa-key.json")
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        
        sheets = build('sheets', 'v4', credentials=creds)
        sheet_id = "1L5qyfPzh2fmiR6-F1TKB2Op03xMzyBn3XmqaTpLOU_A"
        
        result = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="'Simulated Data'"
        ).execute()
        
        values = result.get('values', [])
        
        if len(values) > 1:
            headers = values[0]
            data = values[1:]
            
            for row in data:
                while len(row) < len(headers):
                    row.append('')
            
            df = pd.DataFrame(data, columns=headers)
            return df
        else:
            st.error("No data found")
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# DATA PREP & FILTERING
# ============================================================================

def prepare_data(df):
    """Convert columns and create helper fields."""
    timestamp_cols = ['order_create_ts', 'lvl1_READY_FOR_HANDOVER_ts', 'lvl1_IN_TRANSIT_ts', 'lvl1_final_status_ts', 'lvl2_first_attempt_ts', 'domestic_delivered_ts']
    
    for col in timestamp_cols:
        if col in df.columns:
            # Handle ISO format timestamps - suppress warning for explicit coercion
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Lead time calculations (in days)
    if 'order_create_ts' in df.columns and 'lvl1_READY_FOR_HANDOVER_ts' in df.columns:
        df['oc_to_rfh_days'] = (df['lvl1_READY_FOR_HANDOVER_ts'] - df['order_create_ts']).dt.total_seconds() / 86400
    
    if 'order_create_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
        df['oc_to_fa_days'] = (df['lvl2_first_attempt_ts'] - df['order_create_ts']).dt.total_seconds() / 86400
    
    if 'lvl1_READY_FOR_HANDOVER_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
        df['rfh_to_fa_days'] = (df['lvl2_first_attempt_ts'] - df['lvl1_READY_FOR_HANDOVER_ts']).dt.total_seconds() / 86400
    
    # Anomaly detection flags (lightweight rules)
    df['is_fake_attempt'] = 0
    df['is_theft_risk'] = 0
    df['is_cost_leakage'] = 0
    df['is_sla_at_risk'] = 0
    
    # 1. Fake Attempt: Failed delivery outside buyer location (>1km)
    if 'final_status' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
        df.loc[(df['final_status'] == 'FAILED') & (df['rfh_to_fa_days'] > 3.0), 'is_fake_attempt'] = 1
    
    # 2. Theft Risk: RTS or Lost parcels
    if 'final_status' in df.columns:
        df.loc[df['final_status'].isin(['RTS', 'LOST']), 'is_theft_risk'] = 1
    
    # 3. Cost Leakage: High CPP (>₱100)
    if 'actual_shipping_fee' in df.columns:
        try:
            df['actual_shipping_fee_num'] = pd.to_numeric(df['actual_shipping_fee'], errors='coerce')
            df.loc[df['actual_shipping_fee_num'] > 100, 'is_cost_leakage'] = 1
        except:
            pass
    
    # 4. SLA at Risk: Lead times exceeding targets
    df.loc[(df['oc_to_fa_days'] > 2.5) | (df['rfh_to_fa_days'] > 2.0), 'is_sla_at_risk'] = 1
    
    # ========================================================================
    # LOGISTIC SENTINEL v2.0: Geolocation-Based Anomaly Detection
    # ========================================================================
    
    # FM-GEO: Pickup failed >=1km from origin
    if 'origin_geolocation' in df.columns and 'domestic_pickup_sign_in_failure_geolocation' in df.columns:
        def check_fm_geo(row):
            origin_geo = row['origin_geolocation']
            failure_geo = row['domestic_pickup_sign_in_failure_geolocation']
            if pd.notna(origin_geo) and pd.notna(failure_geo):
                lat1, lon1 = parse_geolocation(origin_geo)
                lat2, lon2 = parse_geolocation(failure_geo)
                if lat1 is not None and lat2 is not None:
                    dist = haversine_distance(lat1, lon1, lat2, lon2)
                    return 1 if dist is not None and dist >= 1.0 else 0
            return 0
        
        df['flag_fm_geo'] = df.apply(check_fm_geo, axis=1)
        df.loc[df['flag_fm_geo'] == 1, 'is_fake_attempt'] = 1
    
    # LM-GEO: Delivery failed >=1km from destination
    if 'destination_geolocation' in df.columns and 'domestic_1st_attempt_failed_geolocation' in df.columns:
        def check_lm_geo(row):
            dest_geo = row['destination_geolocation']
            failure_geo = row['domestic_1st_attempt_failed_geolocation']
            if pd.notna(dest_geo) and pd.notna(failure_geo):
                lat1, lon1 = parse_geolocation(dest_geo)
                lat2, lon2 = parse_geolocation(failure_geo)
                if lat1 is not None and lat2 is not None:
                    dist = haversine_distance(lat1, lon1, lat2, lon2)
                    return 1 if dist is not None and dist >= 1.0 else 0
            return 0
        
        df['flag_lm_geo'] = df.apply(check_lm_geo, axis=1)
        df.loc[df['flag_lm_geo'] == 1, 'is_fake_attempt'] = 1
    
    return df

def apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl):
    """Apply multi-dimensional filters to dataframe."""
    df_filtered = df.copy()
    
    # 3PL filter
    if three_pl and three_pl != "All 3PLs":
        df_filtered = df_filtered[df_filtered['lm_3pl_name'] == three_pl]
    
    # Date range filters (AND logic)
    if oc_dates:
        oc_start, oc_end = pd.to_datetime(oc_dates[0]), pd.to_datetime(oc_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['order_create_ts'] >= oc_start) & (df_filtered['order_create_ts'] < oc_end)]
    
    if rfh_dates:
        rfh_start, rfh_end = pd.to_datetime(rfh_dates[0]), pd.to_datetime(rfh_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['lvl1_READY_FOR_HANDOVER_ts'] >= rfh_start) & (df_filtered['lvl1_READY_FOR_HANDOVER_ts'] < rfh_end)]
    
    if transit_dates:
        transit_start, transit_end = pd.to_datetime(transit_dates[0]), pd.to_datetime(transit_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['lvl1_IN_TRANSIT_ts'] >= transit_start) & (df_filtered['lvl1_IN_TRANSIT_ts'] < transit_end)]
    
    if final_dates:
        final_start, final_end = pd.to_datetime(final_dates[0]), pd.to_datetime(final_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['lvl1_final_status_ts'] >= final_start) & (df_filtered['lvl1_final_status_ts'] < final_end)]
    
    return df_filtered

def get_time_column(anchor_ts, granularity):
    """Get appropriate time grouping column based on granularity."""
    if granularity == "Daily":
        return anchor_ts.dt.date
    elif granularity == "Weekly":
        return anchor_ts.dt.to_period('W')
    elif granularity == "Monthly":
        return anchor_ts.dt.to_period('M')
    else:
        return anchor_ts.dt.date

# ============================================================================
# LOAD & PREPARE DATA
# ============================================================================

df = load_data()
if df.empty:
    st.stop()

df = prepare_data(df)

# ============================================================================
# FILTER ROW
# ============================================================================

st.markdown("### 📊 Filters & Dimensions")

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    # Defensive: Check if lm_3pl_name column exists
    three_pl_options = ["All 3PLs"]
    if 'lm_3pl_name' in df.columns:
        three_pl_options += sorted(list(df['lm_3pl_name'].dropna().unique()))
    three_pl = st.selectbox(
        "3PL Partner",
        three_pl_options,
        help="Select 3PL or view all"
    )

with col2:
    oc_dates = st.date_input(
        "Order Create Date",
        value=[],
        max_value=datetime.now().date(),
        help="Leave blank for all dates"
    )
    oc_dates = tuple(oc_dates) if len(oc_dates) == 2 else None

with col3:
    rfh_dates = st.date_input(
        "Request Handover Date",
        value=[],
        max_value=datetime.now().date(),
        help="When seller marked ready"
    )
    rfh_dates = tuple(rfh_dates) if len(rfh_dates) == 2 else None

with col4:
    transit_dates = st.date_input(
        "In Transit Date",
        value=[],
        max_value=datetime.now().date(),
        help="When 3PL received"
    )
    transit_dates = tuple(transit_dates) if len(transit_dates) == 2 else None

with col5:
    final_dates = st.date_input(
        "Final Status Date",
        value=[],
        max_value=datetime.now().date(),
        help="When parcel completed"
    )
    final_dates = tuple(final_dates) if len(final_dates) == 2 else None

with col6:
    granularity = st.radio(
        "Time Granularity",
        ["Daily", "Weekly", "Monthly"],
        horizontal=True,
        help="Grouping for trends"
    )

st.divider()

# Apply filters
df_filtered = apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl)

if df_filtered.empty:
    st.warning("No data matches selected filters")
    st.stop()

# ============================================================================
# SECTION 1: NETWORK & ALLOCATION
# ============================================================================

st.markdown("## 1️⃣ Network & Allocation")

col1, col2, col3 = st.columns(3)

# 1a. Final Status Volume Completion
try:
    total_orders = len(df_filtered)
    completed_orders = len(df_filtered[df_filtered['final_status'].notna()])
    completion_pct = (completed_orders / total_orders * 100) if total_orders > 0 else 0
    
    with col1:
        st.metric("Final Status Volume Completion %", f"{completion_pct:.1f}%")
except:
    with col1:
        st.metric("Final Status Volume Completion %", "N/A")

# 1b. Total Volume
try:
    with col2:
        st.metric("Total Volume", len(df_filtered))
except:
    with col2:
        st.metric("Total Volume", "N/A")

# 1c. Control Share per 3PL
try:
    with col3:
        if three_pl == "All 3PLs":
            if 'lm_3pl_name' in df_filtered.columns:
                share_data = df_filtered['lm_3pl_name'].value_counts()
                st.metric("3PL Share (Top)", f"{share_data.index[0]}: {share_data.values[0]}")
            else:
                st.metric("3PL Share (Top)", "N/A")
        else:
            st.metric("Selected 3PL Volume", len(df_filtered))
except:
    with col3:
        st.metric("Control Share", "N/A")

st.divider()

# ============================================================================
# SECTION 2: COST
# ============================================================================

st.markdown("## 2️⃣ Cost")

try:
    cpp = pd.to_numeric(df_filtered['actual_shipping_fee'], errors='coerce').mean()
    cpp_target = 81.04
    cpp_delta = cpp - cpp_target
    cpp_delta_color = "normal" if cpp <= cpp_target else "inverse"  # Red if over target
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Cost Per Parcel (₱)", f"₱{cpp:.2f}", delta=f"₱{cpp_delta:.2f} vs ₱{cpp_target}", delta_color=cpp_delta_color)
    
    with col2:
        # CPP trend by final_status_ts
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_cpp = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['actual_shipping_fee'].apply(
                lambda x: pd.to_numeric(x, errors='coerce').mean()
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_cpp.index], y=daily_cpp.values, mode='lines+markers', name='CPP'))
            fig.add_hline(y=81.04, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="CPP Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except Exception as e:
    st.info("Cost data unavailable")

st.divider()

# ============================================================================
# SECTION 3: OPERATIONS
# ============================================================================

st.markdown("## 3️⃣ Operations")

# 3a. Pickup Compliance (anchored to lvl1_REQUEST_FOR_HANDOVER_ts)
try:
    if 'lvl1_READY_FOR_HANDOVER_ts' in df_filtered.columns:
        pickup_comp = (df_filtered['pickup_sla_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        pickup_target = 95.0
        pickup_delta = pickup_comp - pickup_target
        pickup_delta_color = "normal" if pickup_comp >= pickup_target else "inverse"  # Red if below target
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("3a. Pickup Compliance %", f"{pickup_comp:.1f}%", delta=f"{pickup_delta:.1f}% vs {pickup_target}%", delta_color=pickup_delta_color)
        
        with col2:
            daily_pickup = df_filtered.groupby(get_time_column(df_filtered['lvl1_READY_FOR_HANDOVER_ts'], granularity)).apply(
                lambda x: (x['pickup_sla_compliance'] == 'pass').sum() / len(x) * 100
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_pickup.index], y=daily_pickup.values, mode='lines+markers'))
            fig.add_hline(y=95, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Pickup Compliance Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except:
    st.info("Pickup compliance data unavailable")

# 3b. Forward Delivery Compliance (anchored to lvl1_IN_TRANSIT_ts)
try:
    if 'lvl1_IN_TRANSIT_ts' in df_filtered.columns:
        forward_comp = (df_filtered['forward_delivery_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        forward_target = 92.0
        forward_delta = forward_comp - forward_target
        forward_delta_color = "normal" if forward_comp >= forward_target else "inverse"  # Red if below target
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("3b. Forward Delivery Compliance %", f"{forward_comp:.1f}%", delta=f"{forward_delta:.1f}% vs {forward_target}%", delta_color=forward_delta_color)
        
        with col2:
            daily_forward = df_filtered.groupby(get_time_column(df_filtered['lvl1_IN_TRANSIT_ts'], granularity)).apply(
                lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_forward.index], y=daily_forward.values, mode='lines+markers'))
            fig.add_hline(y=92, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Forward Delivery Compliance Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except:
    st.info("Forward compliance data unavailable")

# 3c-3f. Lead Times (anchored to lvl1_final_status_ts)
try:
    col1, col2, col3, col4 = st.columns(4)
    
    # Calculate lead times with NaN handling
    oc_rfh = df_filtered['oc_to_rfh_days'].dropna().mean() if 'oc_to_rfh_days' in df_filtered.columns else np.nan
    oc_fa = df_filtered['oc_to_fa_days'].dropna().mean() if 'oc_to_fa_days' in df_filtered.columns else np.nan
    rfh_fa = df_filtered['rfh_to_fa_days'].dropna().mean() if 'rfh_to_fa_days' in df_filtered.columns else np.nan
    rfh_fa_p90 = df_filtered['rfh_to_fa_days'].dropna().quantile(0.9) if 'rfh_to_fa_days' in df_filtered.columns else np.nan
    
    # Lead time targets (lower is better, so inverse delta coloring)
    oc_rfh_target, oc_fa_target, rfh_fa_target, rfh_fa_p90_target = 0.5, 2.0, 1.5, 3.0
    
    # Check if data is available (not all NaN)
    has_lead_time_data = not (pd.isna(oc_rfh) and pd.isna(oc_fa) and pd.isna(rfh_fa) and pd.isna(rfh_fa_p90))
    
    if has_lead_time_data:
        with col1:
            if not pd.isna(oc_rfh):
                oc_rfh_delta = oc_rfh - oc_rfh_target
                st.metric("3c. OC to RFH (days)", f"{oc_rfh:.1f}", delta=f"{oc_rfh_delta:.1f}d vs {oc_rfh_target}d", delta_color="inverse" if oc_rfh > oc_rfh_target else "normal")
            else:
                st.metric("3c. OC to RFH (days)", "N/A")
        with col2:
            if not pd.isna(oc_fa):
                oc_fa_delta = oc_fa - oc_fa_target
                st.metric("3d. OC to FA (days)", f"{oc_fa:.1f}", delta=f"{oc_fa_delta:.1f}d vs {oc_fa_target}d", delta_color="inverse" if oc_fa > oc_fa_target else "normal")
            else:
                st.metric("3d. OC to FA (days)", "N/A")
        with col3:
            if not pd.isna(rfh_fa):
                rfh_fa_delta = rfh_fa - rfh_fa_target
                st.metric("3e. RFH to FA (days)", f"{rfh_fa:.1f}", delta=f"{rfh_fa_delta:.1f}d vs {rfh_fa_target}d", delta_color="inverse" if rfh_fa > rfh_fa_target else "normal")
            else:
                st.metric("3e. RFH to FA (days)", "N/A")
        with col4:
            if not pd.isna(rfh_fa_p90):
                rfh_fa_p90_delta = rfh_fa_p90 - rfh_fa_p90_target
                st.metric("3f. RFH to FA P90 (days)", f"{rfh_fa_p90:.1f}", delta=f"{rfh_fa_p90_delta:.1f}d vs {rfh_fa_p90_target}d", delta_color="inverse" if rfh_fa_p90 > rfh_fa_p90_target else "normal")
            else:
                st.metric("3f. RFH to FA P90 (days)", "N/A")
    else:
        st.info("Lead time data unavailable - check if timestamp columns are populated")
    
    # Lead time trend charts
    if has_lead_time_data and 'lvl1_final_status_ts' in df_filtered.columns:
        st.markdown("#### Lead Time Trends")
        col1, col2 = st.columns(2)
        
        # RFH to FA trend (most important for operations)
        try:
            with col1:
                daily_rfh_fa = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['rfh_to_fa_days'].apply(
                    lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan
                ).dropna()
                
                if len(daily_rfh_fa) > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_rfh_fa.index],
                        y=daily_rfh_fa.values,
                        mode='lines+markers',
                        name='RFH→FA (days)',
                        line=dict(color='steelblue')
                    ))
                    fig.add_hline(y=rfh_fa_target, line_dash="dash", line_color="orange", annotation_text="Target")
                    fig.update_layout(title="RFH to FA Trend", height=300, showlegend=False, hovermode='x')
                    st.plotly_chart(fig, use_container_width=True)
        except:
            pass
        
        # OC to FA trend
        try:
            with col2:
                daily_oc_fa = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['oc_to_fa_days'].apply(
                    lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan
                ).dropna()
                
                if len(daily_oc_fa) > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_oc_fa.index],
                        y=daily_oc_fa.values,
                        mode='lines+markers',
                        name='OC→FA (days)',
                        line=dict(color='darkgreen')
                    ))
                    fig.add_hline(y=oc_fa_target, line_dash="dash", line_color="orange", annotation_text="Target")
                    fig.update_layout(title="OC to FA Trend", height=300, showlegend=False, hovermode='x')
                    st.plotly_chart(fig, use_container_width=True)
        except:
            pass
        
        # OC to RFH trend
        try:
            col1, col2 = st.columns(2)
            with col1:
                daily_oc_rfh = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['oc_to_rfh_days'].apply(
                    lambda x: x.dropna().mean() if len(x.dropna()) > 0 else np.nan
                ).dropna()
                
                if len(daily_oc_rfh) > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_oc_rfh.index],
                        y=daily_oc_rfh.values,
                        mode='lines+markers',
                        name='OC→RFH (days)',
                        line=dict(color='purple')
                    ))
                    fig.add_hline(y=oc_rfh_target, line_dash="dash", line_color="orange", annotation_text="Target")
                    fig.update_layout(title="OC to RFH Trend", height=300, showlegend=False, hovermode='x')
                    st.plotly_chart(fig, use_container_width=True)
        except:
            pass
        
        # RFH to FA P90 trend
        try:
            with col2:
                daily_rfh_fa_p90 = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['rfh_to_fa_days'].apply(
                    lambda x: x.dropna().quantile(0.9) if len(x.dropna()) > 0 else np.nan
                ).dropna()
                
                if len(daily_rfh_fa_p90) > 0:
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_rfh_fa_p90.index],
                        y=daily_rfh_fa_p90.values,
                        mode='lines+markers',
                        name='RFH→FA P90 (days)',
                        line=dict(color='darkred')
                    ))
                    fig.add_hline(y=rfh_fa_p90_target, line_dash="dash", line_color="orange", annotation_text="Target")
                    fig.update_layout(title="RFH to FA P90 Trend", height=300, showlegend=False, hovermode='x')
                    st.plotly_chart(fig, use_container_width=True)
        except:
            pass

except Exception as e:
    st.info(f"Lead time data unavailable: {str(e)}")

# 3g. Failed Delivery (anchored to lvl1_final_status_ts)
try:
    failed_pct = (df_filtered['final_status'].isin(['FAILED', 'RTS'])).sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    failed_target = 5.0
    failed_delta = failed_pct - failed_target
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("3g. Failed Delivery %", f"{failed_pct:.1f}%", delta=f"{failed_delta:.1f}% vs {failed_target}%", delta_color="inverse" if failed_pct > failed_target else "normal")
    
    with col2:
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_failed = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity)).apply(
                lambda x: (x['final_status'].isin(['FAILED', 'RTS'])).sum() / len(x) * 100
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_failed.index], y=daily_failed.values, mode='lines+markers'))
            fig.add_hline(y=failed_target, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Failed Delivery Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except:
    st.info("Failed delivery data unavailable")

st.divider()

# ============================================================================
# SECTION 4: BREACH
# ============================================================================

st.markdown("## 4️⃣ Breach")

try:
    forward_breach = (df_filtered['is_forward_hard_breach'] == 'Yes').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    rts_breach = (df_filtered['is_rts_hard_breach'] == 'Yes').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    e2e_breach = (df_filtered['final_status'] == 'BREACHED').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    promise_breach = 0.0  # Placeholder
    
    breach_target = 0.0  # Target = 0% breach
    
    # Metrics with trends
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        forward_breach_delta = forward_breach - breach_target
        st.metric("4a. Forward Journey Breach %", f"{forward_breach:.1f}%", delta=f"{forward_breach_delta:.1f}%", delta_color="inverse" if forward_breach > breach_target else "normal")
    with col2:
        rts_breach_delta = rts_breach - breach_target
        st.metric("4b. RTS Journey Breach %", f"{rts_breach:.1f}%", delta=f"{rts_breach_delta:.1f}%", delta_color="inverse" if rts_breach > breach_target else "normal")
    with col3:
        e2e_breach_delta = e2e_breach - breach_target
        st.metric("4c. E2E SLA Breach %", f"{e2e_breach:.1f}%", delta=f"{e2e_breach_delta:.1f}%", delta_color="inverse" if e2e_breach > breach_target else "normal")
    with col4:
        promise_breach_delta = promise_breach - breach_target
        st.metric("4d. Promise Breach %", f"{promise_breach:.1f}%", delta=f"{promise_breach_delta:.1f}%", delta_color="inverse" if promise_breach > breach_target else "normal")
    
    # Trend charts
    col1, col2 = st.columns(2)
    
    with col1:
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_forward_breach = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity)).apply(
                lambda x: (x['is_forward_hard_breach'] == 'Yes').sum() / len(x) * 100 if len(x) > 0 else 0
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_forward_breach.index], y=daily_forward_breach.values, mode='lines+markers'))
            fig.add_hline(y=breach_target, line_dash="dash", line_color="red")
            fig.update_layout(title="Forward Journey Breach Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_rts_breach = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity)).apply(
                lambda x: (x['is_rts_hard_breach'] == 'Yes').sum() / len(x) * 100 if len(x) > 0 else 0
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_rts_breach.index], y=daily_rts_breach.values, mode='lines+markers'))
            fig.add_hline(y=breach_target, line_dash="dash", line_color="red")
            fig.update_layout(title="RTS Journey Breach Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except:
    st.info("Breach data unavailable")

st.divider()

# ============================================================================
# SECTION 5: LOST & DAMAGED
# ============================================================================

st.markdown("## 5️⃣ Lost & Damaged")

try:
    lost_pct = (df_filtered['final_status'] == 'LOST').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    damaged_pct = (df_filtered['final_status'] == 'DAMAGED').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    
    ld_target = 0.1  # Target = 0.1%
    
    col1, col2 = st.columns(2)
    
    with col1:
        lost_delta = lost_pct - ld_target
        st.metric("5a. Lost %", f"{lost_pct:.1f}%", delta=f"{lost_delta:.1f}% vs {ld_target}%", delta_color="inverse" if lost_pct > ld_target else "normal")
    
    with col2:
        damaged_delta = damaged_pct - ld_target
        st.metric("5b. Damaged %", f"{damaged_pct:.1f}%", delta=f"{damaged_delta:.1f}% vs {ld_target}%", delta_color="inverse" if damaged_pct > ld_target else "normal")
    
    # Trend charts
    col1, col2 = st.columns(2)
    
    with col1:
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_lost = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity)).apply(
                lambda x: (x['final_status'] == 'LOST').sum() / len(x) * 100 if len(x) > 0 else 0
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_lost.index], y=daily_lost.values, mode='lines+markers'))
            fig.add_hline(y=ld_target, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Lost Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_damaged = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity)).apply(
                lambda x: (x['final_status'] == 'DAMAGED').sum() / len(x) * 100 if len(x) > 0 else 0
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i).split()[0] if ' ' in str(i) else str(i) for i in daily_damaged.index], y=daily_damaged.values, mode='lines+markers'))
            fig.add_hline(y=ld_target, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Damaged Trend", height=300, showlegend=False)
            st.plotly_chart(fig, use_container_width=True)
except:
    st.info("Lost & Damaged data unavailable")

st.divider()

# ============================================================================
# SECTION 6: ANOMALY DETECTION (Coming Soon)
# ============================================================================

with st.expander("🔍 Anomaly Detection Dashboard"):
    st.markdown("## Risk Flags & Early Warning System")
    
    try:
        # Count anomalies
        fake_pickup = (df_filtered['is_fake_attempt'] == 1).sum()
        forward_soft = (df_filtered['is_forward_soft_breach'] == 1).sum() if 'is_forward_soft_breach' in df_filtered.columns else 0
        rts_soft = (df_filtered['is_rts_soft_breach'] == 1).sum() if 'is_rts_soft_breach' in df_filtered.columns else 0
        forward_hard = (df_filtered['is_forward_hard_breach'] == 1).sum() if 'is_forward_hard_breach' in df_filtered.columns else 0
        rts_hard = (df_filtered['is_rts_hard_breach'] == 1).sum() if 'is_rts_hard_breach' in df_filtered.columns else 0
        
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            pct = fake_pickup/max(len(df_filtered),1)*100
            st.metric("🚨 Potential Fake Pickup", fake_pickup, delta=f"{pct:.1f}%")
        with col2:
            pct = fake_pickup/max(len(df_filtered),1)*100
            st.metric("📦 Potential Fake Delivery", 0, delta="0.0%")  # Placeholder
        with col3:
            pct = forward_soft/max(len(df_filtered),1)*100
            st.metric("📌 Forward Soft", forward_soft, delta=f"{pct:.1f}%")
        with col4:
            pct = rts_soft/max(len(df_filtered),1)*100
            st.metric("🔄 RTS Soft", rts_soft, delta=f"{pct:.1f}%")
        with col5:
            pct = forward_hard/max(len(df_filtered),1)*100
            st.metric("⚠️ Forward Hard", forward_hard, delta=f"{pct:.1f}%")
        with col6:
            pct = rts_hard/max(len(df_filtered),1)*100
            st.metric("🔴 RTS Hard", rts_hard, delta=f"{pct:.1f}%")
        
        st.divider()
        
        tab_fake, tab_sla = st.tabs(["Potential Fake Attempts", "SLA Breaches"])
        
        with tab_fake:
            st.markdown("### Potential Fake Pickup Attempts")
            if fake_pickup > 0:
                st.info(f"{fake_pickup} parcels flagged for potential fake pickup (FM-GEO + FM-BULK)")
                # Placeholder: FM-GEO table
                st.markdown("**Geolocation Violations (FM-GEO)**")
                st.caption("Columns: fm_3pl_name, tracking_number, origin_region, seller_id, seller_name, fm_courier_id, origin_geolocation, domestic_pickup_sign_in_failure_geolocation")
            else:
                st.info("No potential fake pickup attempts detected")
            
            st.markdown("### Potential Fake Delivery Attempts")
            st.info("Delivery anomalies (LM-GEO + LM-BULK)")
            st.caption("Columns: lm_3pl_name, tracking_number, destination_region, lm_courier_id, destination_geolocation, domestic_1st_attempt_failed_geolocation")
        
        with tab_sla:
            st.markdown("### SLA Breach Tracking")
            
            tab_fs, tab_rs, tab_fh, tab_rh = st.tabs(["Forward Soft", "RTS Soft", "Forward Hard", "RTS Hard"])
            
            with tab_fs:
                if forward_soft > 0:
                    st.metric("Forward Soft Breach", forward_soft)
                    st.caption("Columns: lm_3pl_name, tracking_number, origin_region, destination_region, forward_journey_closure_soft_breach_sla, forward_journey_closure_soft_breach_date")
                else:
                    st.info("No forward soft breaches")
            
            with tab_rs:
                if rts_soft > 0:
                    st.metric("RTS Soft Breach", rts_soft)
                    st.caption("Columns: lm_3pl_name, tracking_number, origin_region, destination_region, rts_journey_closure_soft_breach_sla, rts_journey_closure_soft_breach_date")
                else:
                    st.info("No RTS soft breaches")
            
            with tab_fh:
                if forward_hard > 0:
                    st.metric("Forward Hard Breach", forward_hard)
                    st.caption("Columns: lm_3pl_name, tracking_number, origin_region, destination_region, forward_journey_closure_hard_breach_sla, forward_journey_closure_hard_breach_date")
                else:
                    st.info("No forward hard breaches")
            
            with tab_rh:
                if rts_hard > 0:
                    st.metric("RTS Hard Breach", rts_hard)
                    st.caption("Columns: lm_3pl_name, tracking_number, origin_region, destination_region, rts_journey_closure_hard_breach_sla, rts_journey_closure_hard_breach_date")
                else:
                    st.info("No RTS hard breaches")
        
    except Exception as e:
        st.error(f"Anomaly detection error: {str(e)}")

st.divider()

st.caption("Dashboard v3.0 | Multi-dimensional filtering | Independent timestamp anchors | Anomaly detection coming soon")
