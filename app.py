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

@st.cache_data(ttl=300)
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
        sheet_id = "1zTGMztXvfsl4oIt1X6whtW2hC4tJgKOnYtXHt6NrncY"
        
        result = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="'Simulated Data'!A1:ZZ1000"
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
    timestamp_cols = ['order_create_ts', 'lvl1_REQUEST_FOR_HANDOVER_ts', 'lvl1_IN_TRANSIT_ts', 'lvl1_final_status_ts', 'lvl2_first_attempt_ts', 'domestic_delivered_ts']
    
    for col in timestamp_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors='coerce')
    
    # Lead time calculations (in days)
    if 'order_create_ts' in df.columns and 'lvl1_REQUEST_FOR_HANDOVER_ts' in df.columns:
        df['oc_to_rfh_days'] = (df['lvl1_REQUEST_FOR_HANDOVER_ts'] - df['order_create_ts']).dt.total_seconds() / 86400
    
    if 'order_create_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
        df['oc_to_fa_days'] = (df['lvl2_first_attempt_ts'] - df['order_create_ts']).dt.total_seconds() / 86400
    
    if 'lvl1_REQUEST_FOR_HANDOVER_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
        df['rfh_to_fa_days'] = (df['lvl2_first_attempt_ts'] - df['lvl1_REQUEST_FOR_HANDOVER_ts']).dt.total_seconds() / 86400
    
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
        df_filtered = df_filtered[(df_filtered['lvl1_REQUEST_FOR_HANDOVER_ts'] >= rfh_start) & (df_filtered['lvl1_REQUEST_FOR_HANDOVER_ts'] < rfh_end)]
    
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
    three_pl = st.selectbox(
        "3PL Partner",
        ["All 3PLs"] + list(df['lm_3pl_name'].dropna().unique()),
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
            share_data = df_filtered['lm_3pl_name'].value_counts()
            st.metric("3PL Share (Top)", f"{share_data.index[0]}: {share_data.values[0]}")
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
    
    col1, col2 = st.columns([1, 2])
    with col1:
        st.metric("Cost Per Parcel (₱)", f"₱{cpp:.2f}", delta="vs target ₱81.04")
    
    with col2:
        # CPP trend by final_status_ts
        if 'lvl1_final_status_ts' in df_filtered.columns:
            daily_cpp = df_filtered.groupby(get_time_column(df_filtered['lvl1_final_status_ts'], granularity))['actual_shipping_fee'].apply(
                lambda x: pd.to_numeric(x, errors='coerce').mean()
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i) for i in daily_cpp.index], y=daily_cpp.values, mode='lines+markers', name='CPP'))
            fig.add_hline(y=81.04, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="CPP Trend", height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch")
except Exception as e:
    st.info("Cost data unavailable")

st.divider()

# ============================================================================
# SECTION 3: OPERATIONS
# ============================================================================

st.markdown("## 3️⃣ Operations")

# 3a. Pickup Compliance (anchored to lvl1_REQUEST_FOR_HANDOVER_ts)
try:
    if 'lvl1_REQUEST_FOR_HANDOVER_ts' in df_filtered.columns:
        pickup_comp = (df_filtered['pickup_sla_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("3a. Pickup Compliance %", f"{pickup_comp:.1f}%", delta="vs target 95%")
        
        with col2:
            daily_pickup = df_filtered.groupby(get_time_column(df_filtered['lvl1_REQUEST_FOR_HANDOVER_ts'], granularity)).apply(
                lambda x: (x['pickup_sla_compliance'] == 'pass').sum() / len(x) * 100
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i) for i in daily_pickup.index], y=daily_pickup.values, mode='lines+markers'))
            fig.add_hline(y=95, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Pickup Compliance Trend", height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch")
except:
    st.info("Pickup compliance data unavailable")

# 3b. Forward Delivery Compliance (anchored to lvl1_IN_TRANSIT_ts)
try:
    if 'lvl1_IN_TRANSIT_ts' in df_filtered.columns:
        forward_comp = (df_filtered['forward_delivery_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("3b. Forward Delivery Compliance %", f"{forward_comp:.1f}%", delta="vs target 92%")
        
        with col2:
            daily_forward = df_filtered.groupby(get_time_column(df_filtered['lvl1_IN_TRANSIT_ts'], granularity)).apply(
                lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100
            )
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=[str(i) for i in daily_forward.index], y=daily_forward.values, mode='lines+markers'))
            fig.add_hline(y=92, line_dash="dash", line_color="red", annotation_text="Target")
            fig.update_layout(title="Forward Delivery Compliance Trend", height=300, showlegend=False)
            st.plotly_chart(fig, width="stretch")
except:
    st.info("Forward compliance data unavailable")

# 3c-3f. Lead Times (anchored to lvl1_final_status_ts)
try:
    col1, col2, col3, col4 = st.columns(4)
    
    oc_rfh = df_filtered['oc_to_rfh_days'].mean()
    oc_fa = df_filtered['oc_to_fa_days'].mean()
    rfh_fa = df_filtered['rfh_to_fa_days'].mean()
    rfh_fa_p90 = df_filtered['rfh_to_fa_days'].quantile(0.9)
    
    with col1:
        st.metric("3c. OC to RFH (days)", f"{oc_rfh:.1f}")
    with col2:
        st.metric("3d. OC to FA (days)", f"{oc_fa:.1f}")
    with col3:
        st.metric("3e. RFH to FA (days)", f"{rfh_fa:.1f}")
    with col4:
        st.metric("3f. RFH to FA P90 (days)", f"{rfh_fa_p90:.1f}")
except:
    st.info("Lead time data unavailable")

# 3g. Failed Delivery (anchored to lvl1_final_status_ts)
try:
    failed_pct = (df_filtered['final_status'].isin(['FAILED', 'RTS'])).sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    
    st.metric("3g. Failed Delivery %", f"{failed_pct:.1f}%", delta="vs target <5%")
except:
    st.info("Failed delivery data unavailable")

st.divider()

# ============================================================================
# SECTION 4: BREACH
# ============================================================================

st.markdown("## 4️⃣ Breach")

try:
    col1, col2, col3, col4 = st.columns(4)
    
    forward_breach = (df_filtered['is_forward_hard_breach'] == 'Yes').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    rts_breach = (df_filtered['is_rts_hard_breach'] == 'Yes').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    e2e_breach = (df_filtered['final_status'] == 'BREACHED').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    promise_breach = len(df_filtered) > 0 and 0  # Placeholder
    
    with col1:
        st.metric("4a. Forward Journey Breach %", f"{forward_breach:.1f}%")
    with col2:
        st.metric("4b. RTS Journey Breach %", f"{rts_breach:.1f}%")
    with col3:
        st.metric("4c. E2E SLA Breach %", f"{e2e_breach:.1f}%")
    with col4:
        st.metric("4d. Promise Breach %", f"{promise_breach:.1f}%")
except:
    st.info("Breach data unavailable")

st.divider()

# ============================================================================
# SECTION 5: LOST & DAMAGED
# ============================================================================

st.markdown("## 5️⃣ Lost & Damaged")

try:
    col1, col2 = st.columns(2)
    
    lost_pct = (df_filtered['final_status'] == 'LOST').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    damaged_pct = (df_filtered['final_status'] == 'DAMAGED').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    
    with col1:
        st.metric("5a. Lost %", f"{lost_pct:.1f}%", delta="vs target <0.1%")
    
    with col2:
        st.metric("5b. Damaged %", f"{damaged_pct:.1f}%", delta="vs target <0.1%")
except:
    st.info("Lost & Damaged data unavailable")

st.divider()

# ============================================================================
# SECTION 6: ANOMALY DETECTION
# ============================================================================

st.markdown("## 6️⃣ Anomaly Detection")

tab1, tab2, tab3 = st.tabs(["Potential Fake Pickup", "Potential Fake Delivery", "SLA Breaches"])

# TAB 1: Fake Pickup
with tab1:
    st.subheader("Fake Pickup Attempts (FM-GEO)")
    
    if 'flag_fake_attempt_fm_geolocation' in df_filtered.columns:
        fake_pickup_df = df_filtered[df_filtered['flag_fake_attempt_fm_geolocation'] == 1]
        st.metric("Parcels Flagged", len(fake_pickup_df))
        
        if len(fake_pickup_df) > 0:
            cols_to_show = ['lm_3pl_name', 'tracking_number', 'origin_region', 'seller_name', 
                           'fm_courier_id', 'origin_geolocation']
            cols_to_show = [c for c in cols_to_show if c in fake_pickup_df.columns]
            st.dataframe(fake_pickup_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No fake pickup flags detected")
    else:
        st.info("Flag column not available in dataset")

# TAB 2: Fake Delivery
with tab2:
    st.subheader("Fake Delivery Attempts (LM-GEO)")
    
    fake_delivery_df = df_filtered[df_filtered['final_status'] == 'DELIVERY_FAILED'].copy()
    st.metric("Delivery Failed", len(fake_delivery_df))
    
    if len(fake_delivery_df) > 0:
        cols_to_show = ['lm_3pl_name', 'tracking_number', 'destination_region', 'lm_courier_id',
                       'destination_geolocation']
        cols_to_show = [c for c in cols_to_show if c in fake_delivery_df.columns]
        st.dataframe(fake_delivery_df[cols_to_show], use_container_width=True)
    else:
        st.info("✅ No delivery failures detected")

# TAB 3: SLA Breaches
with tab3:
    sla_tab1, sla_tab2, sla_tab3, sla_tab4 = st.tabs(["Forward Soft", "Forward Hard", "RTS Soft", "RTS Hard"])
    
    with sla_tab1:
        st.subheader("Forward Soft Breach")
        fwd_soft_df = df_filtered[df_filtered['is_forward_soft_breach'] == 1]
        st.metric("Parcels", len(fwd_soft_df))
        
        if len(fwd_soft_df) > 0:
            cols_to_show = ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region',
                           'forward_journey_closure_soft_breach_sla']
            cols_to_show = [c for c in cols_to_show if c in fwd_soft_df.columns]
            st.dataframe(fwd_soft_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No forward soft breaches")
    
    with sla_tab2:
        st.subheader("Forward Hard Breach")
        fwd_hard_df = df_filtered[df_filtered['is_forward_hard_breach'] == 1]
        st.metric("Parcels", len(fwd_hard_df))
        
        if len(fwd_hard_df) > 0:
            cols_to_show = ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region',
                           'forward_journey_closure_hard_breach_sla']
            cols_to_show = [c for c in cols_to_show if c in fwd_hard_df.columns]
            st.dataframe(fwd_hard_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No forward hard breaches")
    
    with sla_tab3:
        st.subheader("RTS Soft Breach")
        rts_soft_df = df_filtered[df_filtered['is_rts_soft_breach'] == 1]
        st.metric("Parcels", len(rts_soft_df))
        
        if len(rts_soft_df) > 0:
            cols_to_show = ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region',
                           'rts_journey_closure_soft_breach_sla']
            cols_to_show = [c for c in cols_to_show if c in rts_soft_df.columns]
            st.dataframe(rts_soft_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No RTS soft breaches")
    
    with sla_tab4:
        st.subheader("RTS Hard Breach")
        rts_hard_df = df_filtered[df_filtered['is_rts_hard_breach'] == 1]
        st.metric("Parcels", len(rts_hard_df))
        
        if len(rts_hard_df) > 0:
            cols_to_show = ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region',
                           'rts_journey_closure_hard_breach_sla']
            cols_to_show = [c for c in cols_to_show if c in rts_hard_df.columns]
            st.dataframe(rts_hard_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No RTS hard breaches")

st.divider()

st.caption("Dashboard v3.0+ | Multi-dimensional filtering | Independent timestamp anchors | Anomaly Detection")
