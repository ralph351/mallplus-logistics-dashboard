"""
MallPlus Logistics Dashboard v3.1 - Fixed Data Handling
Comprehensive KPI dashboard with anomaly detection
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

st.title("🚚 MallPlus Logistics Dashboard v3.2")
st.markdown("**Professional Multi-Dimensional Analytics** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8"))

# ============================================================================
# DATA LOADING
# ============================================================================

@st.cache_data(ttl=60)
def load_data():
    """Load data from Google Sheets - handle duplicates gracefully."""
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
            
            # Handle duplicate columns by keeping first occurrence
            seen = {}
            unique_headers = []
            duplicate_indices = set()
            
            for i, col in enumerate(headers):
                if col in seen:
                    duplicate_indices.add(i)
                else:
                    seen[col] = i
                    unique_headers.append(col)
            
            # Filter out duplicate columns
            filtered_data = []
            for row in data:
                filtered_row = [val for i, val in enumerate(row) if i not in duplicate_indices]
                while len(filtered_row) < len(unique_headers):
                    filtered_row.append('')
                filtered_data.append(filtered_row)
            
            df = pd.DataFrame(filtered_data, columns=unique_headers)
            return df
        else:
            st.error("No data found in sheet")
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Error loading data: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# DATA PREP
# ============================================================================

def prepare_data(df):
    """Prepare data: convert timestamps, ensure columns exist."""
    # Safe timestamp conversion
    timestamp_cols = ['order_create_ts', 'lvl1_READY_FOR_HANDOVER_ts', 'lvl1_IN_TRANSIT_ts',
                      'lvl1_final_status_ts', 'lvl2_first_attempt_ts', 'domestic_delivered_ts']
    
    for col in timestamp_cols:
        if col in df.columns:
            try:
                df[col] = pd.to_datetime(df[col], errors='coerce')
            except:
                pass
    
    # Ensure numeric columns
    numeric_cols = ['system_chargeable_weight', 'actual_chargeable_weight', 
                    'estimated_shipping_fee', 'actual_shipping_fee',
                    'forward_journey_closure_soft_breach_sla', 'forward_journey_closure_hard_breach_sla',
                    'rts_journey_closure_soft_breach_sla', 'rts_journey_closure_hard_breach_sla']
    
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
    
    # Ensure flag columns are numeric (0/1)
    flag_cols = ['flag_fake_attempt_fm_geolocation', 'is_forward_soft_breach', 'is_forward_hard_breach',
                 'is_rts_soft_breach', 'is_rts_hard_breach']
    
    for col in flag_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)
    
    return df

# ============================================================================
# LOAD & PREPARE
# ============================================================================

df = load_data()
if df.empty:
    st.error("📊 Failed to load data. Please check your Google Sheets connection.")
    st.stop()

st.info(f"✅ Loaded {len(df)} orders with {len(df.columns)} columns")

df = prepare_data(df)

# ============================================================================
# FILTERS
# ============================================================================

st.markdown("### 📊 Filters")
col1, col2, col3, col4 = st.columns(4)

with col1:
    three_pl_options = ["All 3PLs"]
    if 'lm_3pl_name' in df.columns:
        three_pl_options += sorted(df['lm_3pl_name'].dropna().unique().tolist())
    three_pl = st.selectbox("3PL Partner", three_pl_options, help="Select 3PL or view all")

with col2:
    if 'order_create_ts' in df.columns and pd.api.types.is_datetime64_any_dtype(df['order_create_ts']):
        min_date = df['order_create_ts'].min().date()
        max_date = df['order_create_ts'].max().date()
        oc_dates = st.date_input("Order Create Date Range", value=[min_date, max_date], max_value=datetime.now().date())
    else:
        oc_dates = []

with col3:
    if 'destination_region' in df.columns:
        region_options = ["All Regions"] + sorted(df['destination_region'].dropna().unique().tolist())
        region = st.selectbox("Destination Region", region_options)
    else:
        region = "All Regions"

with col4:
    if 'lvl1_order_logistics_status' in df.columns:
        status_options = ["All Status"] + sorted(df['lvl1_order_logistics_status'].dropna().unique().tolist())
        status = st.selectbox("Order Status", status_options)
    else:
        status = "All Status"

# Apply filters
df_filtered = df.copy()

if three_pl and three_pl != "All 3PLs" and 'lm_3pl_name' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['lm_3pl_name'] == three_pl]

if oc_dates and len(oc_dates) == 2 and 'order_create_ts' in df_filtered.columns:
    oc_start = pd.to_datetime(oc_dates[0])
    oc_end = pd.to_datetime(oc_dates[1]) + timedelta(days=1)
    df_filtered = df_filtered[(df_filtered['order_create_ts'] >= oc_start) & (df_filtered['order_create_ts'] < oc_end)]

if region != "All Regions" and 'destination_region' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['destination_region'] == region]

if status != "All Status" and 'lvl1_order_logistics_status' in df_filtered.columns:
    df_filtered = df_filtered[df_filtered['lvl1_order_logistics_status'] == status]

# ============================================================================
# KPI METRICS
# ============================================================================

st.markdown("### 📈 Summary Metrics")

col1, col2, col3, col4, col5, col6 = st.columns(6)

# Total Orders
with col1:
    st.metric("Total Orders", len(df_filtered))

# Delivered
with col2:
    delivered = len(df_filtered[df_filtered['final_status'] == 'DELIVERED']) if 'final_status' in df_filtered.columns else 0
    st.metric("Delivered", delivered, f"{delivered/len(df_filtered)*100:.1f}%" if len(df_filtered) > 0 else "0%")

# Delivery Failed
with col3:
    failed = len(df_filtered[df_filtered['final_status'] == 'DELIVERY_FAILED']) if 'final_status' in df_filtered.columns else 0
    st.metric("Failed", failed)

# Fake Pickup Attempts
with col4:
    fake_pickup = df_filtered['flag_fake_attempt_fm_geolocation'].sum() if 'flag_fake_attempt_fm_geolocation' in df_filtered.columns else 0
    st.metric("🚨 Fake Pickup Flags", int(fake_pickup))

# Forward Soft Breach
with col5:
    fwd_soft = df_filtered['is_forward_soft_breach'].sum() if 'is_forward_soft_breach' in df_filtered.columns else 0
    st.metric("⚠️ Forward Soft Breach", int(fwd_soft))

# Forward Hard Breach
with col6:
    fwd_hard = df_filtered['is_forward_hard_breach'].sum() if 'is_forward_hard_breach' in df_filtered.columns else 0
    st.metric("🔴 Forward Hard Breach", int(fwd_hard))

# ============================================================================
# SECTION 1: NETWORK
# ============================================================================

st.markdown("### 🌐 Network Performance")

col1, col2 = st.columns(2)

with col1:
    if 'destination_region' in df_filtered.columns and 'lvl1_order_logistics_status' in df_filtered.columns:
        region_status = df_filtered.groupby('destination_region')['lvl1_order_logistics_status'].value_counts().unstack(fill_value=0)
        st.dataframe(region_status, use_container_width=True)

with col2:
    if 'lm_3pl_name' in df_filtered.columns and 'final_status' in df_filtered.columns:
        threepl_status = df_filtered.groupby('lm_3pl_name')['final_status'].value_counts().unstack(fill_value=0)
        st.dataframe(threepl_status, use_container_width=True)

# ============================================================================
# SECTION 2: ANOMALY DETECTION
# ============================================================================

st.markdown("### 🔍 Anomaly Detection")

tab1, tab2, tab3 = st.tabs(["Potential Fake Pickup", "Potential Fake Delivery", "SLA Breaches"])

# TAB 1: Fake Pickup
with tab1:
    st.subheader("Fake Pickup Attempts (FM-GEO)")
    
    if 'flag_fake_attempt_fm_geolocation' in df_filtered.columns:
        fake_pickup_df = df_filtered[df_filtered['flag_fake_attempt_fm_geolocation'] == 1]
        st.metric("Parcels Flagged", len(fake_pickup_df))
        
        if len(fake_pickup_df) > 0:
            cols_to_show = ['fm_3pl_name', 'tracking_number', 'origin_region', 'seller_name', 
                           'fm_courier_id', 'origin_geolocation', 'domestic_pickup_sign_in_failure_geolocation']
            cols_to_show = [c for c in cols_to_show if c in fake_pickup_df.columns]
            st.dataframe(fake_pickup_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No fake pickup flags detected")
    else:
        st.warning("Column not found")

# TAB 2: Fake Delivery
with tab2:
    st.subheader("Fake Delivery Attempts (LM-GEO)")
    
    fake_delivery_df = df_filtered[df_filtered['final_status'] == 'DELIVERY_FAILED'].copy()
    st.metric("Delivery Failed", len(fake_delivery_df))
    
    if len(fake_delivery_df) > 0:
        cols_to_show = ['lm_3pl_name', 'tracking_number', 'destination_region', 'lm_courier_id',
                       'destination_geolocation', 'domestic_1st_attempt_failed_geolocation', 'fd_triggered_geo_flags']
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
                           'forward_journey_closure_soft_breach_sla', 'forward_journey_closure_soft_breach_date']
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
                           'forward_journey_closure_hard_breach_sla', 'forward_journey_closure_hard_breach_date']
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
                           'rts_journey_closure_soft_breach_sla', 'rts_journey_closure_soft_breach_date']
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
                           'rts_journey_closure_hard_breach_sla', 'rts_journey_closure_hard_breach_date']
            cols_to_show = [c for c in cols_to_show if c in rts_hard_df.columns]
            st.dataframe(rts_hard_df[cols_to_show], use_container_width=True)
        else:
            st.info("✅ No RTS hard breaches")

# ============================================================================
# DEBUG
# ============================================================================

if st.checkbox("🔧 Debug - Show Data Sample"):
    st.subheader("Data Sample")
    st.write(f"Rows: {len(df_filtered)}, Columns: {len(df_filtered.columns)}")
    st.dataframe(df_filtered.head(10), use_container_width=True)
    
    st.subheader("Column Names")
    st.write(df_filtered.columns.tolist())
