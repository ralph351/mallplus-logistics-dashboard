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
st.markdown("**Professional Multi-Dimensional Analytics** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8") + " | Ready ✅")

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
    """Convert columns and create helper fields. Robust handling of missing columns."""
    try:
        # Timestamp columns that may exist
        timestamp_cols = ['order_create_ts', 'lvl1_READY_FOR_HANDOVER_ts', 'lvl1_IN_TRANSIT_ts', 'lvl1_final_status_ts', 'lvl2_first_attempt_ts']
        
        for col in timestamp_cols:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col], errors='coerce', format='ISO8601')
        
        # Initialize lead time columns with NaN (safe default)
        df['oc_to_rfh_days'] = np.nan
        df['oc_to_fa_days'] = np.nan
        df['rfh_to_fa_days'] = np.nan
        df['rfh_to_fa_p90'] = np.nan
        
        # Calculate only if both columns exist
        if 'order_create_ts' in df.columns and 'lvl1_READY_FOR_HANDOVER_ts' in df.columns:
            valid_mask = df['order_create_ts'].notna() & df['lvl1_READY_FOR_HANDOVER_ts'].notna()
            if valid_mask.any():
                df.loc[valid_mask, 'oc_to_rfh_days'] = (df.loc[valid_mask, 'lvl1_READY_FOR_HANDOVER_ts'] - df.loc[valid_mask, 'order_create_ts']).dt.total_seconds() / 86400
        
        if 'order_create_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
            valid_mask = df['order_create_ts'].notna() & df['lvl2_first_attempt_ts'].notna()
            if valid_mask.any():
                df.loc[valid_mask, 'oc_to_fa_days'] = (df.loc[valid_mask, 'lvl2_first_attempt_ts'] - df.loc[valid_mask, 'order_create_ts']).dt.total_seconds() / 86400
        
        if 'lvl1_READY_FOR_HANDOVER_ts' in df.columns and 'lvl2_first_attempt_ts' in df.columns:
            valid_mask = df['lvl1_READY_FOR_HANDOVER_ts'].notna() & df['lvl2_first_attempt_ts'].notna()
            if valid_mask.any():
                df.loc[valid_mask, 'rfh_to_fa_days'] = (df.loc[valid_mask, 'lvl2_first_attempt_ts'] - df.loc[valid_mask, 'lvl1_READY_FOR_HANDOVER_ts']).dt.total_seconds() / 86400
    
        # Add KPI flags for final status analysis
        df['is_delivered'] = (df['final_status'] == 'DELIVERED').astype(int)
        df['is_failed_delivery'] = df['final_status'].isin(['RETURNED']).astype(int)
        df['is_package_damaged'] = (df['final_status'] == 'PACKAGE_DAMAGED').astype(int)
        df['is_package_lost'] = (df['final_status'] == 'PACKAGE_LOST').astype(int)
        df['is_package_cancelled'] = (df['final_status'] == 'PACKAGE_CANCELLED').astype(int)
        
    except Exception as e:
        st.warning(f"Data prep issue: {str(e)}")
    
    return df


def compute_anomalies(df):
    """Compute anomaly detection: FM/LM geolocation flags + EOD failure rate analysis."""
    try:
        from math import radians, cos, sin, asin, sqrt
        
        def haversine(lon1, lat1, lon2, lat2):
            try:
                lon1, lat1, lon2, lat2 = map(radians, [float(lon1), float(lat1), float(lon2), float(lat2)])
                dlon, dlat = lon2 - lon1, lat2 - lat1
                a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
                return 6371 * 2 * asin(sqrt(a))
            except: return 0
        
        def parse_geo(s):
            try:
                if pd.isna(s) or s == '': return None
                p = str(s).split(',')
                return (float(p[0].strip()), float(p[1].strip())) if len(p) >= 2 else None
            except: return None
        
        # === GEOLOCATION FLAGS ===
        # FM Geolocation: >1km from origin
        df['flag_fake_attempt_fm_geolocation'] = 0
        if 'origin_geolocation' in df.columns and 'domestic_pickup/sign_in_failure_geolocation' in df.columns:
            for idx in range(len(df)):
                o = parse_geo(df.iloc[idx]['origin_geolocation'])
                f = parse_geo(df.iloc[idx]['domestic_pickup/sign_in_failure_geolocation'])
                if o and f and haversine(o[1], o[0], f[1], f[0]) >= 1.0:
                    df.at[idx, 'flag_fake_attempt_fm_geolocation'] = 1
        
        # LM Geolocation: >1km from destination (check all three attempt types)
        df['flag_fake_attempt_lm_geolocation'] = 0
        df['fd_flag_fake_attempt_detailed'] = None
        
        if 'destination_geolocation' in df.columns:
            for idx in range(len(df)):
                d = parse_geo(df.iloc[idx]['destination_geolocation'])
                if not d:
                    continue
                
                # Check all three delivery attempt geolocations
                flags = []
                
                # 1st attempt
                if 'domestic_1st_attempt_failed_geolocation' in df.columns:
                    f1 = parse_geo(df.iloc[idx]['domestic_1st_attempt_failed_geolocation'])
                    if f1 and haversine(d[1], d[0], f1[1], f1[0]) >= 1.0:
                        flags.append('1st Attempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
                # Reattempts
                if 'domestic_reattempts_failed_geolocation' in df.columns:
                    fr = parse_geo(df.iloc[idx]['domestic_reattempts_failed_geolocation'])
                    if fr and haversine(d[1], d[0], fr[1], fr[0]) >= 1.0:
                        flags.append('Reattempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
                # Final delivery
                if 'domestic_delivery_failed_geolocation' in df.columns:
                    ff = parse_geo(df.iloc[idx]['domestic_delivery_failed_geolocation'])
                    if ff and haversine(d[1], d[0], ff[1], ff[0]) >= 1.0:
                        flags.append('Final Attempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
                # Build detailed flag message
                if flags:
                    attempts_str = ', '.join(flags)
                    df.at[idx, 'fd_flag_fake_attempt_detailed'] = f"Potential Fake Attempt - Geotagged >1km away at: {attempts_str}"
        
        # === FM EOD FAILURE RATE ===
        df['fm_activity_day'] = None
        df['fm_eod_failure_rate_pct'] = None
        df['fm_failure_tier'] = None
        
        try:
            if 'lvl2_domestic_pickup/sign_in_failure_ts' in df.columns and 'fm_courier_id' in df.columns:
                df['lvl2_domestic_pickup/sign_in_failure_ts'] = pd.to_datetime(df['lvl2_domestic_pickup/sign_in_failure_ts'], errors='coerce')
                
                fm_with_ts = df[df['lvl2_domestic_pickup/sign_in_failure_ts'].notna()].copy()
                if not fm_with_ts.empty:
                    fm_with_ts['fm_activity_day'] = fm_with_ts['lvl2_domestic_pickup/sign_in_failure_ts'].dt.date
                    
                    # Aggregate: count failures per courier per day, find last event
                    fm_daily = fm_with_ts.groupby(['fm_courier_id', 'fm_activity_day']).agg(
                        fm_total=('lvl2_domestic_pickup/sign_in_failure_ts', 'count'),
                        fm_last_ts=('lvl2_domestic_pickup/sign_in_failure_ts', 'max')
                    ).reset_index()
                    
                    # Count failures in last 30 mins
                    fm_daily['fm_30m_cutoff'] = fm_daily['fm_last_ts'] - pd.Timedelta(minutes=30)
                    fm_daily['fm_last_30m'] = fm_daily.apply(
                        lambda r: len(fm_with_ts[(fm_with_ts['fm_courier_id'] == r['fm_courier_id']) & 
                                                 (fm_with_ts['fm_activity_day'] == r['fm_activity_day']) & 
                                                 (fm_with_ts['lvl2_domestic_pickup/sign_in_failure_ts'] >= r['fm_30m_cutoff'])]), axis=1
                    )
                    
                    # Calculate rate
                    fm_daily['fm_eod_failure_rate_pct'] = (fm_daily['fm_last_30m'] / fm_daily['fm_total'] * 100).round(2)
                    fm_daily['fm_failure_tier'] = fm_daily['fm_eod_failure_rate_pct'].apply(
                        lambda x: 'a. FM Courier Failure Rate 20% and below' if x <= 20
                        else 'b. FM Courier Failure Rate 50% and below' if x <= 50
                        else 'c. Potential Fake Attempt - FM Courier Failure Rate above 50%'
                    )
                    
                    # Merge back
                    for _, row in fm_daily.iterrows():
                        mask = (df['fm_courier_id'] == row['fm_courier_id']) & \
                               (df['lvl2_domestic_pickup/sign_in_failure_ts'].notna()) & \
                               (df['lvl2_domestic_pickup/sign_in_failure_ts'].dt.date == row['fm_activity_day'])
                        df.loc[mask, 'fm_activity_day'] = row['fm_activity_day']
                        df.loc[mask, 'fm_eod_failure_rate_pct'] = row['fm_eod_failure_rate_pct']
                        df.loc[mask, 'fm_failure_tier'] = row['fm_failure_tier']
        except Exception as e:
            pass
        
        # === LM EOD FAILURE RATE ===
        df['lm_activity_day'] = None
        df['lm_eod_failure_rate_pct'] = None
        df['lm_failure_tier'] = None
        
        try:
            if 'lm_courier_id' in df.columns:
                # Convert timestamps
                for col in ['lvl2_domestic_1st_attempt_failed_ts', 'lvl2_domestic_reattempts_failed_ts', 'lvl2_domestic_delivery_failed_ts']:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                
                # Unpivot all three failure types
                lm_events = []
                for col in ['lvl2_domestic_1st_attempt_failed_ts', 'lvl2_domestic_reattempts_failed_ts', 'lvl2_domestic_delivery_failed_ts']:
                    if col in df.columns:
                        temp = df[df[col].notna()][['lm_courier_id', col]].copy()
                        temp.columns = ['lm_courier_id', 'lm_failure_ts']
                        lm_events.append(temp)
                
                if lm_events:
                    lm_all = pd.concat(lm_events, ignore_index=True)
                    if not lm_all.empty:
                        lm_all['lm_activity_day'] = lm_all['lm_failure_ts'].dt.date
                        
                        # Aggregate per courier per day
                        lm_daily = lm_all.groupby(['lm_courier_id', 'lm_activity_day']).agg(
                            lm_total=('lm_failure_ts', 'count'),
                            lm_last_ts=('lm_failure_ts', 'max')
                        ).reset_index()
                        
                        # Count last 30 mins
                        lm_daily['lm_30m_cutoff'] = lm_daily['lm_last_ts'] - pd.Timedelta(minutes=30)
                        lm_daily['lm_last_30m'] = lm_daily.apply(
                            lambda r: len(lm_all[(lm_all['lm_courier_id'] == r['lm_courier_id']) & 
                                                (lm_all['lm_activity_day'] == r['lm_activity_day']) & 
                                                (lm_all['lm_failure_ts'] >= r['lm_30m_cutoff'])]), axis=1
                        )
                        
                        # Calculate rate
                        lm_daily['lm_eod_failure_rate_pct'] = (lm_daily['lm_last_30m'] / lm_daily['lm_total'] * 100).round(2)
                        lm_daily['lm_failure_tier'] = lm_daily['lm_eod_failure_rate_pct'].apply(
                            lambda x: 'a. LM Courier Failure Rate 20% and below' if x <= 20
                            else 'b. LM Courier Failure Rate 50% and below' if x <= 50
                            else 'c. Potential Fake Attempt - LM Courier Failure Rate above 50%'
                        )
                        
                        # Merge back
                        for _, row in lm_daily.iterrows():
                            mask = (df['lm_courier_id'] == row['lm_courier_id'])
                            for ts_col in ['lvl2_domestic_1st_attempt_failed_ts', 'lvl2_domestic_reattempts_failed_ts', 'lvl2_domestic_delivery_failed_ts']:
                                if ts_col in df.columns:
                                    ts_mask = (df[ts_col].notna()) & (df[ts_col].dt.date == row['lm_activity_day'])
                                    df.loc[mask & ts_mask, 'lm_activity_day'] = row['lm_activity_day']
                                    df.loc[mask & ts_mask, 'lm_eod_failure_rate_pct'] = row['lm_eod_failure_rate_pct']
                                    df.loc[mask & ts_mask, 'lm_failure_tier'] = row['lm_failure_tier']
        except Exception as e:
            pass
    
    except Exception as e:
        pass
    
    return df

def apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl, origin_region=None, origin_address_id=None, dest_region=None, dest_address_id=None):
    """Apply multi-dimensional filters to dataframe. Safe column checking."""
    df_filtered = df.copy()
    
    # 3PL filter (only if column exists)
    if three_pl and three_pl != "All 3PLs" and 'lm_3pl_name' in df.columns:
        df_filtered = df_filtered[df_filtered['lm_3pl_name'] == three_pl]
    
    # Origin Region filter
    if origin_region and origin_region != "All Regions" and 'origin_region' in df.columns:
        df_filtered = df_filtered[df_filtered['origin_region'] == origin_region]
    
    # Origin Address ID filter
    if origin_address_id and origin_address_id != "All Addresses" and 'lvl2_origin_address_id' in df.columns:
        df_filtered = df_filtered[df_filtered['lvl2_origin_address_id'] == origin_address_id]
    
    # Destination Region filter
    if dest_region and dest_region != "All Regions" and 'destination_region' in df.columns:
        df_filtered = df_filtered[df_filtered['destination_region'] == dest_region]
    
    # Destination Address ID filter
    if dest_address_id and dest_address_id != "All Addresses" and 'lvl2_destination_address_id' in df.columns:
        df_filtered = df_filtered[df_filtered['lvl2_destination_address_id'] == dest_address_id]
    
    # Date range filters (AND logic) - only apply if column exists
    if oc_dates and 'order_create_ts' in df.columns:
        oc_start, oc_end = pd.to_datetime(oc_dates[0]), pd.to_datetime(oc_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['order_create_ts'] >= oc_start) & (df_filtered['order_create_ts'] < oc_end)]
    
    if rfh_dates and 'lvl1_READY_FOR_HANDOVER_ts' in df.columns:
        rfh_start, rfh_end = pd.to_datetime(rfh_dates[0]), pd.to_datetime(rfh_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['lvl1_READY_FOR_HANDOVER_ts'] >= rfh_start) & (df_filtered['lvl1_READY_FOR_HANDOVER_ts'] < rfh_end)]
    
    if transit_dates and 'lvl1_IN_TRANSIT_ts' in df.columns:
        transit_start, transit_end = pd.to_datetime(transit_dates[0]), pd.to_datetime(transit_dates[1]) + timedelta(days=1)
        df_filtered = df_filtered[(df_filtered['lvl1_IN_TRANSIT_ts'] >= transit_start) & (df_filtered['lvl1_IN_TRANSIT_ts'] < transit_end)]
    
    if final_dates and 'lvl1_final_status_ts' in df.columns:
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

def create_trend_line(df_filtered, metric_column, metric_label, metric_format=".1f", granularity="Daily", is_percentage=False):
    """Create trend line chart for a metric grouped by lvl1_final_status_ts with time granularity."""
    try:
        if 'lvl1_final_status_ts' not in df_filtered.columns or df_filtered.empty:
            return None
        
        # Create time grouping
        df_trend = df_filtered.copy()
        df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
        
        # Calculate metric by time bucket
        if metric_column == 'lead_time' or 'days' in metric_column:
            # For lead time metrics (mean)
            trend_data = df_trend.groupby('time_bucket')[metric_column].mean().reset_index()
        elif metric_column == 'p90':
            # For P90 percentile
            trend_data = df_trend.groupby('time_bucket')['rfh_to_fa_days'].quantile(0.9).reset_index()
            trend_data.columns = ['time_bucket', metric_column]
        else:
            # For percentage metrics (count / total * 100)
            trend_data = df_trend.groupby('time_bucket')[metric_column].apply(
                lambda x: (x == 1).sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_data.columns = ['time_bucket', metric_column]
        
        trend_data = trend_data.sort_values('time_bucket')
        
        if trend_data.empty:
            return None
        
        # Create line chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=trend_data['time_bucket'].astype(str),
            y=trend_data[metric_column],
            mode='lines+markers',
            name=metric_label,
            line=dict(color='#1f77b4', width=2),
            marker=dict(size=6)
        ))
        
        y_label = "% " if is_percentage else "Days"
        
        fig.update_layout(
            title=f"{metric_label} Trend",
            xaxis_title=f"{granularity} (Final Status Date)",
            yaxis_title=y_label,
            hovermode='x unified',
            height=300,
            margin=dict(l=50, r=50, t=50, b=50),
            showlegend=False
        )
        
        return fig
    except Exception as e:
        st.warning(f"Trend line error for {metric_label}: {str(e)}")
        return None

# ============================================================================
# LOAD & PREPARE DATA
# ============================================================================

df = load_data()
if df.empty:
    st.stop()

df = prepare_data(df)
df = compute_anomalies(df)

# ============================================================================
# FILTER ROW
# ============================================================================

st.markdown("### 📊 Filters & Dimensions")

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    # Safely get 3PL list
    three_pl_options = ["All 3PLs"]
    if 'lm_3pl_name' in df.columns:
        three_pl_options += list(df['lm_3pl_name'].dropna().unique())
    three_pl = st.selectbox(
        "3PL Partner",
        three_pl_options,
        help="Select 3PL or view all"
    )

with col2:
    # Origin Region filter
    origin_region_options = ["All Regions"]
    if 'origin_region' in df.columns:
        origin_region_options += list(df['origin_region'].dropna().unique())
    origin_region = st.selectbox(
        "Origin Region",
        origin_region_options,
        help="Select origin region or view all"
    )

with col3:
    # Origin Address ID filter (depends on origin_region selection)
    origin_address_options = ["All Addresses"]
    if 'lvl2_origin_address_id' in df.columns:
        if origin_region != "All Regions":
            filtered_by_origin_region = df[df['origin_region'] == origin_region]
            origin_address_options += list(filtered_by_origin_region['lvl2_origin_address_id'].dropna().unique())
        else:
            origin_address_options += list(df['lvl2_origin_address_id'].dropna().unique())
    origin_address_id = st.selectbox(
        "Origin Address ID",
        origin_address_options,
        help="Select origin address or view all"
    )

with col4:
    # Destination Region filter
    dest_region_options = ["All Regions"]
    if 'destination_region' in df.columns:
        dest_region_options += list(df['destination_region'].dropna().unique())
    dest_region = st.selectbox(
        "Destination Region",
        dest_region_options,
        help="Select destination region or view all"
    )

with col5:
    # Destination Address ID filter (depends on dest_region selection)
    dest_address_options = ["All Addresses"]
    if 'lvl2_destination_address_id' in df.columns:
        if dest_region != "All Regions":
            filtered_by_dest_region = df[df['destination_region'] == dest_region]
            dest_address_options += list(filtered_by_dest_region['lvl2_destination_address_id'].dropna().unique())
        else:
            dest_address_options += list(df['lvl2_destination_address_id'].dropna().unique())
    dest_address_id = st.selectbox(
        "Destination Address ID",
        dest_address_options,
        help="Select destination address or view all"
    )

with col6:
    granularity = st.radio(
        "Time Granularity",
        ["Daily", "Weekly", "Monthly"],
        horizontal=True,
        help="Grouping for trends"
    )

st.divider()

# Row 2: Date filters (moved below geographic filters for better UX)
col_d1, col_d2, col_d3, col_d4 = st.columns(4)

with col_d1:
    oc_dates = st.date_input(
        "Order Create Date",
        value=[],
        max_value=datetime.now().date(),
        help="Leave blank for all dates"
    )
    oc_dates = tuple(oc_dates) if len(oc_dates) == 2 else None

with col_d2:
    rfh_dates = st.date_input(
        "Request Handover Date",
        value=[],
        max_value=datetime.now().date(),
        help="When seller marked ready"
    )
    rfh_dates = tuple(rfh_dates) if len(rfh_dates) == 2 else None

with col_d3:
    transit_dates = st.date_input(
        "In Transit Date",
        value=[],
        max_value=datetime.now().date(),
        help="When 3PL received"
    )
    transit_dates = tuple(transit_dates) if len(transit_dates) == 2 else None

with col_d4:
    final_dates = st.date_input(
        "Final Status Date",
        value=[],
        max_value=datetime.now().date(),
        help="When parcel completed"
    )
    final_dates = tuple(final_dates) if len(final_dates) == 2 else None

st.divider()

# Apply filters (now includes geographic filters)
df_filtered = apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl, 
                           origin_region, origin_address_id, dest_region, dest_address_id)

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
    # Count only non-empty final_status (exclude blank strings)
    completed_orders = len(df_filtered[(df_filtered['final_status'].notna()) & (df_filtered['final_status'] != '')])
    completion_pct = (completed_orders / total_orders * 100) if total_orders > 0 else 0
    
    with col1:
        st.metric("Final Status Volume Completion %", f"{completion_pct:.1f}%")
except:
    with col1:
        st.metric("Final Status Volume Completion %", "N/A")

# 1b. Total Volume & In-Transit Count
try:
    with col2:
        in_transit = len(df_filtered[(df_filtered['final_status'].isna()) | (df_filtered['final_status'] == '')])
        st.metric("Total Volume", f"{len(df_filtered)} ({in_transit} in-transit)")
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

# 1d. 3PL Volume Control Pie Chart
try:
    if three_pl == "All 3PLs":
        three_pl_volumes = df_filtered['lm_3pl_name'].value_counts()
        if len(three_pl_volumes) > 0:
            fig_pie = go.Figure(data=[go.Pie(
                labels=three_pl_volumes.index,
                values=three_pl_volumes.values,
                hovertemplate='<b>%{label}</b><br>Volume: %{value}<br>%{percent}<extra></extra>'
            )])
            fig_pie.update_layout(
                title="3PL Volume Control",
                height=350,
                showlegend=True
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No 3PL data available")
    else:
        st.info(f"Filtered to {three_pl} only. View 'All 3PLs' to see volume distribution.")
except Exception as e:
    st.info("3PL volume chart unavailable")

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
            x_labels = [str(i).split(' ')[0] if ' ' in str(i) else str(i) for i in daily_cpp.index]
            fig.add_trace(go.Scatter(x=x_labels, y=daily_cpp.values, mode='lines+markers', name='CPP'))
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

# ============ OPERATIONS SCORECARD (NEW) ============
st.markdown("### Operations Scorecard - Dynamic Pivot Table")

try:
    # Define available dimensions
    available_dimensions = []
    if 'origin_region' in df_filtered.columns:
        available_dimensions.append('origin_region')
    if 'lvl2_origin_address_id' in df_filtered.columns:
        available_dimensions.append('lvl2_origin_address_id')
    if 'destination_region' in df_filtered.columns:
        available_dimensions.append('destination_region')
    if 'lvl2_destination_address_id' in df_filtered.columns:
        available_dimensions.append('lvl2_destination_address_id')
    if 'lm_3pl_name' in df_filtered.columns:
        available_dimensions.append('lm_3pl_name')
    
    if available_dimensions:
        # User selects which dimensions to include
        selected_dimensions = st.multiselect(
            "Select Row Dimensions for Scorecard",
            available_dimensions,
            default=available_dimensions[:2] if len(available_dimensions) >= 2 else available_dimensions,
            help="Choose which dimensions to pivot by"
        )
        
        if selected_dimensions:
            # Prepare data for pivot table
            pivot_data = df_filtered.copy()
            
            # Calculate KPI values
            # 3a. Pickup Compliance %
            if 'pickup_sla_compliance' in pivot_data.columns:
                pivot_data['pickup_compliance'] = (pivot_data['pickup_sla_compliance'] == 'pass').astype(int)
            else:
                pivot_data['pickup_compliance'] = 0
            
            # 3b. Forward Delivery Compliance %
            if 'forward_delivery_compliance' in pivot_data.columns:
                pivot_data['forward_compliance'] = (pivot_data['forward_delivery_compliance'] == 'pass').astype(int)
            else:
                pivot_data['forward_compliance'] = 0
            
            # 3c-3f. Lead times already calculated in prepare_data()
            # 3g. Failed Delivery %
            if 'final_status' in pivot_data.columns:
                pivot_data['failed_delivery'] = pivot_data['final_status'].isin(['FAILED', 'RTS']).astype(int)
            else:
                pivot_data['failed_delivery'] = 0
            
            # Build aggregation dictionary
            agg_dict = {
                'pickup_compliance': ['sum', 'count'],
                'forward_compliance': ['sum', 'count'],
                'oc_to_rfh_days': 'mean',
                'oc_to_fa_days': 'mean',
                'rfh_to_fa_days': 'mean',
                'failed_delivery': ['sum', 'count']
            }
            
            # Perform groupby aggregation
            scorecard = pivot_data.groupby(selected_dimensions, dropna=False).agg(agg_dict).reset_index()
            
            # Flatten multi-level column names
            scorecard.columns = ['_'.join(col).strip('_') if col[1] else col[0] for col in scorecard.columns.values]
            
            # Rename for readability
            rename_map = {
                'pickup_compliance_sum': 'Pickup_Pass',
                'pickup_compliance_count': 'Pickup_Total',
                'forward_compliance_sum': 'Forward_Pass',
                'forward_compliance_count': 'Forward_Total',
                'oc_to_rfh_days_mean': 'OC_to_RFH_days',
                'oc_to_fa_days_mean': 'OC_to_FA_days',
                'rfh_to_fa_days_mean': 'RFH_to_FA_days',
                'failed_delivery_sum': 'Failed_Count',
                'failed_delivery_count': 'Delivery_Total'
            }
            scorecard = scorecard.rename(columns=rename_map)
            
            # Add p90 calculation - properly reset index with names
            p90_data = pivot_data.groupby(selected_dimensions)['rfh_to_fa_days'].quantile(0.9).reset_index(name='rfh_to_fa_p90')
            
            # Merge p90 data
            scorecard = scorecard.merge(p90_data, on=selected_dimensions, how='left')
            
            # Calculate percentages (handle division by zero)
            scorecard['Pickup_Compliance_%'] = (scorecard['Pickup_Pass'] / scorecard['Pickup_Total'].replace(0, np.nan) * 100).round(2)
            scorecard['Forward_Compliance_%'] = (scorecard['Forward_Pass'] / scorecard['Forward_Total'].replace(0, np.nan) * 100).round(2)
            scorecard['Failed_Delivery_%'] = (scorecard['Failed_Count'] / scorecard['Delivery_Total'].replace(0, np.nan) * 100).round(2)
            
            # Build final display dataframe (drop intermediate columns)
            display_cols = selected_dimensions + [
                'Pickup_Compliance_%',
                'Forward_Compliance_%',
                'OC_to_RFH_days',
                'OC_to_FA_days',
                'RFH_to_FA_days',
                'rfh_to_fa_p90',
                'Failed_Delivery_%'
            ]
            display_cols = [col for col in display_cols if col in scorecard.columns]
            scorecard_display = scorecard[display_cols].copy()
            
            # Rename for final display
            scorecard_display = scorecard_display.rename(columns={
                'origin_region': 'Origin Region',
                'lvl2_origin_address_id': 'Origin Address',
                'destination_region': 'Destination Region',
                'lvl2_destination_address_id': 'Destination Address',
                'lm_3pl_name': '3PL Partner',
                'Pickup_Compliance_%': '3a. Pickup Compliance %',
                'Forward_Compliance_%': '3b. Forward Compliance %',
                'OC_to_RFH_days': '3c. OC→RFH (days)',
                'OC_to_FA_days': '3d. OC→FA (days)',
                'RFH_to_FA_days': '3e. RFH→FA (days)',
                'rfh_to_fa_p90': '3f. RFH→FA P90 (days)',
                'Failed_Delivery_%': '3g. Failed Delivery %'
            })
            
            # Sort by first dimension
            if len(selected_dimensions) > 0:
                first_dim_display = selected_dimensions[0].replace('lvl2_', '').replace('_', ' ').title()
                scorecard_display = scorecard_display.sort_values(
                    by=[col for col in scorecard_display.columns if 'Region' in col or 'Address' in col or '3PL' in col][0],
                    na_position='last'
                )
            
            # Display with numeric formatting
            st.dataframe(
                scorecard_display.style.format({
                    col: '{:.2f}' for col in scorecard_display.columns 
                    if '%' in col or 'days' in col.lower() or 'P90' in col
                }),
                use_container_width=True,
                height=400
            )
            
            st.caption(f"📊 Scorecard: {len(scorecard_display)} row(s) × {len(display_cols)} metrics | Filters: {', '.join(selected_dimensions)}")
        else:
            st.info("Select at least one dimension to view the scorecard")
    else:
        st.warning("No geographic/3PL dimensions available in data")

except Exception as e:
    st.error(f"Scorecard error: {str(e)}")

st.divider()

# 3a. Pickup Compliance (anchored to lvl1_READY_FOR_HANDOVER_ts)
try:
    if 'lvl1_READY_FOR_HANDOVER_ts' in df_filtered.columns:
        pickup_comp = (df_filtered['pickup_sla_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        
        col1, col2 = st.columns([1, 2])
        with col1:
            st.metric("3a. Pickup Compliance %", f"{pickup_comp:.1f}%", delta="vs target 95%")
        
        with col2:
            daily_pickup = df_filtered.groupby(get_time_column(df_filtered['lvl1_READY_FOR_HANDOVER_ts'], granularity)).apply(
                lambda x: (x['pickup_sla_compliance'] == 'pass').sum() / len(x) * 100
            )
            
            fig = go.Figure()
            x_labels = [str(i).split(' ')[0] if ' ' in str(i) else str(i) for i in daily_pickup.index]
            fig.add_trace(go.Scatter(x=x_labels, y=daily_pickup.values, mode='lines+markers'))
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
            x_labels = [str(i).split(' ')[0] if ' ' in str(i) else str(i) for i in daily_forward.index]
            fig.add_trace(go.Scatter(x=x_labels, y=daily_forward.values, mode='lines+markers'))
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
    
    # Trend lines for lead times
    col_trend1, col_trend2, col_trend3, col_trend4 = st.columns(4)
    
    with col_trend1:
        df_trend_oc_rfh = df_filtered[df_filtered['oc_to_rfh_days'].notna()].copy()
        if not df_trend_oc_rfh.empty and 'lvl1_final_status_ts' in df_trend_oc_rfh.columns:
            df_trend_oc_rfh['time_bucket'] = get_time_column(df_trend_oc_rfh['lvl1_final_status_ts'], granularity)
            trend_oc_rfh = df_trend_oc_rfh.groupby('time_bucket')['oc_to_rfh_days'].mean().reset_index().sort_values('time_bucket')
            if not trend_oc_rfh.empty:
                fig_oc_rfh = go.Figure()
                fig_oc_rfh.add_trace(go.Scatter(x=trend_oc_rfh['time_bucket'].astype(str), y=trend_oc_rfh['oc_to_rfh_days'],
                    mode='lines+markers', line=dict(color='#1f77b4', width=2), marker=dict(size=5)))
                fig_oc_rfh.update_layout(title="OC to RFH Trend", xaxis_title=f"{granularity}", yaxis_title="Days",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_oc_rfh, use_container_width=True)
    
    with col_trend2:
        df_trend_oc_fa = df_filtered[df_filtered['oc_to_fa_days'].notna()].copy()
        if not df_trend_oc_fa.empty and 'lvl1_final_status_ts' in df_trend_oc_fa.columns:
            df_trend_oc_fa['time_bucket'] = get_time_column(df_trend_oc_fa['lvl1_final_status_ts'], granularity)
            trend_oc_fa = df_trend_oc_fa.groupby('time_bucket')['oc_to_fa_days'].mean().reset_index().sort_values('time_bucket')
            if not trend_oc_fa.empty:
                fig_oc_fa = go.Figure()
                fig_oc_fa.add_trace(go.Scatter(x=trend_oc_fa['time_bucket'].astype(str), y=trend_oc_fa['oc_to_fa_days'],
                    mode='lines+markers', line=dict(color='#2ca02c', width=2), marker=dict(size=5)))
                fig_oc_fa.update_layout(title="OC to FA Trend", xaxis_title=f"{granularity}", yaxis_title="Days",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_oc_fa, use_container_width=True)
    
    with col_trend3:
        df_trend_rfh_fa = df_filtered[df_filtered['rfh_to_fa_days'].notna()].copy()
        if not df_trend_rfh_fa.empty and 'lvl1_final_status_ts' in df_trend_rfh_fa.columns:
            df_trend_rfh_fa['time_bucket'] = get_time_column(df_trend_rfh_fa['lvl1_final_status_ts'], granularity)
            trend_rfh_fa = df_trend_rfh_fa.groupby('time_bucket')['rfh_to_fa_days'].mean().reset_index().sort_values('time_bucket')
            if not trend_rfh_fa.empty:
                fig_rfh_fa = go.Figure()
                fig_rfh_fa.add_trace(go.Scatter(x=trend_rfh_fa['time_bucket'].astype(str), y=trend_rfh_fa['rfh_to_fa_days'],
                    mode='lines+markers', line=dict(color='#d62728', width=2), marker=dict(size=5)))
                fig_rfh_fa.update_layout(title="RFH to FA Trend", xaxis_title=f"{granularity}", yaxis_title="Days",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_rfh_fa, use_container_width=True)
    
    with col_trend4:
        df_trend_p90 = df_filtered[df_filtered['rfh_to_fa_days'].notna()].copy()
        if not df_trend_p90.empty and 'lvl1_final_status_ts' in df_trend_p90.columns:
            df_trend_p90['time_bucket'] = get_time_column(df_trend_p90['lvl1_final_status_ts'], granularity)
            trend_p90 = df_trend_p90.groupby('time_bucket')['rfh_to_fa_days'].quantile(0.9).reset_index().sort_values('time_bucket')
            trend_p90.columns = ['time_bucket', 'p90']
            if not trend_p90.empty:
                fig_p90 = go.Figure()
                fig_p90.add_trace(go.Scatter(x=trend_p90['time_bucket'].astype(str), y=trend_p90['p90'],
                    mode='lines+markers', line=dict(color='#9467bd', width=2), marker=dict(size=5)))
                fig_p90.update_layout(title="RFH to FA P90 Trend", xaxis_title=f"{granularity}", yaxis_title="Days",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_p90, use_container_width=True)
except:
    st.info("Lead time data unavailable")

# 3g. Failed Delivery (anchored to lvl1_final_status_ts)
try:
    # 3g: Failed Delivery % = Failed / (Delivered + Failed)
    # Only count completed orders (exclude in-transit)
    completed_mask = (df_filtered['final_status'] != '') & (df_filtered['final_status'].notna())
    delivered_count = (df_filtered[completed_mask]['final_status'] == 'DELIVERED').sum()
    failed_count = (df_filtered[completed_mask]['final_status'].isin(['RETURNED', 'PACKAGE_DAMAGED', 'PACKAGE_LOST'])).sum()
    total_completed = delivered_count + failed_count
    
    failed_pct = (failed_count / total_completed * 100) if total_completed > 0 else 0
    
    st.metric("3g. Failed Delivery %", f"{failed_pct:.1f}%", delta="vs target <5%")
    
    # Trend line for Failed Delivery %
    df_trend_fd = df_filtered.copy()
    if 'lvl1_final_status_ts' in df_trend_fd.columns and not df_trend_fd.empty:
        df_trend_fd['time_bucket'] = get_time_column(df_trend_fd['lvl1_final_status_ts'], granularity)
        trend_fd = df_trend_fd.groupby('time_bucket').apply(
            lambda x: (
                (x['final_status'].isin(['RETURNED', 'PACKAGE_DAMAGED', 'PACKAGE_LOST'])).sum() / 
                ((x['final_status'] == 'DELIVERED').sum() + (x['final_status'].isin(['RETURNED', 'PACKAGE_DAMAGED', 'PACKAGE_LOST'])).sum()) * 100
            ) if (x['final_status'] == 'DELIVERED').sum() + (x['final_status'].isin(['RETURNED', 'PACKAGE_DAMAGED', 'PACKAGE_LOST'])).sum() > 0 else 0
        ).reset_index()
        trend_fd.columns = ['time_bucket', 'failed_pct']
        trend_fd = trend_fd.sort_values('time_bucket')
        
        if not trend_fd.empty:
            fig_fd = go.Figure()
            fig_fd.add_trace(go.Scatter(
                x=trend_fd['time_bucket'].astype(str),
                y=trend_fd['failed_pct'],
                mode='lines+markers',
                name='Failed Delivery %',
                line=dict(color='#ff7f0e', width=2),
                marker=dict(size=6)
            ))
            fig_fd.update_layout(
                title="Failed Delivery % Trend",
                xaxis_title=f"{granularity} (Final Status Date)",
                yaxis_title="%",
                hovermode='x unified',
                height=300,
                margin=dict(l=50, r=50, t=50, b=50),
                showlegend=False
            )
            st.plotly_chart(fig_fd, use_container_width=True)
except:
    st.info("Failed delivery data unavailable")

st.divider()

# ============================================================================
# SECTION 4: BREACH
# ============================================================================

st.markdown("## 4️⃣ Breach")

try:
    col1, col2, col3, col4 = st.columns(4)
    
    forward_breach = (df_filtered['is_forward_hard_breach'].astype(str) == '1').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    rts_breach = (df_filtered['is_rts_hard_breach'].astype(str) == '1').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    e2e_breach = ((df_filtered['is_forward_hard_breach'].astype(str) == '1') | (df_filtered['is_rts_hard_breach'].astype(str) == '1')).sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    promise_breach = len(df_filtered) > 0 and 0  # Placeholder
    
    with col1:
        st.metric("4a. Forward Journey Breach %", f"{forward_breach:.1f}%")
    with col2:
        st.metric("4b. RTS Journey Breach %", f"{rts_breach:.1f}%")
    with col3:
        st.metric("4c. E2E SLA Breach %", f"{e2e_breach:.1f}%")
    with col4:
        st.metric("4d. Promise Breach %", f"{promise_breach:.1f}%")
    
    # Trend lines for breach metrics
    col_breach1, col_breach2, col_breach3, col_breach4 = st.columns(4)
    
    with col_breach1:
        df_trend_fwd = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend_fwd.columns and not df_trend_fwd.empty:
            df_trend_fwd['time_bucket'] = get_time_column(df_trend_fwd['lvl1_final_status_ts'], granularity)
            trend_fwd = df_trend_fwd.groupby('time_bucket').apply(
                lambda x: (x['is_forward_hard_breach'].astype(str) == '1').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_fwd.columns = ['time_bucket', 'fwd_breach']
            trend_fwd = trend_fwd.sort_values('time_bucket')
            if not trend_fwd.empty:
                fig_fwd = go.Figure()
                fig_fwd.add_trace(go.Scatter(x=trend_fwd['time_bucket'].astype(str), y=trend_fwd['fwd_breach'],
                    mode='lines+markers', line=dict(color='#1f77b4', width=2), marker=dict(size=5)))
                fig_fwd.update_layout(title="Forward Breach % Trend", xaxis_title=f"{granularity}", yaxis_title="%",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_fwd, use_container_width=True)
    
    with col_breach2:
        df_trend_rts = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend_rts.columns and not df_trend_rts.empty:
            df_trend_rts['time_bucket'] = get_time_column(df_trend_rts['lvl1_final_status_ts'], granularity)
            trend_rts = df_trend_rts.groupby('time_bucket').apply(
                lambda x: (x['is_rts_hard_breach'].astype(str) == '1').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_rts.columns = ['time_bucket', 'rts_breach']
            trend_rts = trend_rts.sort_values('time_bucket')
            if not trend_rts.empty:
                fig_rts = go.Figure()
                fig_rts.add_trace(go.Scatter(x=trend_rts['time_bucket'].astype(str), y=trend_rts['rts_breach'],
                    mode='lines+markers', line=dict(color='#2ca02c', width=2), marker=dict(size=5)))
                fig_rts.update_layout(title="RTS Breach % Trend", xaxis_title=f"{granularity}", yaxis_title="%",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_rts, use_container_width=True)
    
    with col_breach3:
        df_trend_e2e = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend_e2e.columns and not df_trend_e2e.empty:
            df_trend_e2e['time_bucket'] = get_time_column(df_trend_e2e['lvl1_final_status_ts'], granularity)
            trend_e2e = df_trend_e2e.groupby('time_bucket').apply(
                lambda x: (x['final_status'] == 'BREACHED').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_e2e.columns = ['time_bucket', 'e2e_breach']
            trend_e2e = trend_e2e.sort_values('time_bucket')
            if not trend_e2e.empty:
                fig_e2e = go.Figure()
                fig_e2e.add_trace(go.Scatter(x=trend_e2e['time_bucket'].astype(str), y=trend_e2e['e2e_breach'],
                    mode='lines+markers', line=dict(color='#d62728', width=2), marker=dict(size=5)))
                fig_e2e.update_layout(title="E2E SLA Breach % Trend", xaxis_title=f"{granularity}", yaxis_title="%",
                    height=250, margin=dict(l=40, r=40, t=40, b=40), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_e2e, use_container_width=True)
    
    with col_breach4:
        st.info("Promise Breach trend: TBD")
except:
    st.info("Breach data unavailable")

st.divider()

# ============================================================================
# SECTION 5: LOST & DAMAGED
# ============================================================================

st.markdown("## 5️⃣ Lost & Damaged")

try:
    col1, col2 = st.columns(2)
    
    lost_pct = (df_filtered['is_package_lost'].sum()) / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    damaged_pct = (df_filtered['is_package_damaged'].sum()) / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
    
    with col1:
        st.metric("5a. Lost %", f"{lost_pct:.1f}%", delta="vs target <0.1%")
    
    with col2:
        st.metric("5b. Damaged %", f"{damaged_pct:.1f}%", delta="vs target <0.1%")
    
    # Trend lines for Lost & Damaged
    col_loss1, col_loss2 = st.columns(2)
    
    with col_loss1:
        df_trend_lost = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend_lost.columns and not df_trend_lost.empty:
            df_trend_lost['time_bucket'] = get_time_column(df_trend_lost['lvl1_final_status_ts'], granularity)
            trend_lost = df_trend_lost.groupby('time_bucket').apply(
                lambda x: (x['final_status'] == 'LOST').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_lost.columns = ['time_bucket', 'lost_pct']
            trend_lost = trend_lost.sort_values('time_bucket')
            if not trend_lost.empty:
                fig_lost = go.Figure()
                fig_lost.add_trace(go.Scatter(x=trend_lost['time_bucket'].astype(str), y=trend_lost['lost_pct'],
                    mode='lines+markers', line=dict(color='#ff7f0e', width=2), marker=dict(size=6)))
                fig_lost.update_layout(title="Lost % Trend", xaxis_title=f"{granularity} (Final Status Date)", yaxis_title="%",
                    height=300, margin=dict(l=50, r=50, t=50, b=50), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_lost, use_container_width=True)
    
    with col_loss2:
        df_trend_dmg = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend_dmg.columns and not df_trend_dmg.empty:
            df_trend_dmg['time_bucket'] = get_time_column(df_trend_dmg['lvl1_final_status_ts'], granularity)
            trend_dmg = df_trend_dmg.groupby('time_bucket').apply(
                lambda x: (x['final_status'] == 'DAMAGED').sum() / len(x) * 100 if len(x) > 0 else 0
            ).reset_index()
            trend_dmg.columns = ['time_bucket', 'dmg_pct']
            trend_dmg = trend_dmg.sort_values('time_bucket')
            if not trend_dmg.empty:
                fig_dmg = go.Figure()
                fig_dmg.add_trace(go.Scatter(x=trend_dmg['time_bucket'].astype(str), y=trend_dmg['dmg_pct'],
                    mode='lines+markers', line=dict(color='#d62728', width=2), marker=dict(size=6)))
                fig_dmg.update_layout(title="Damaged % Trend", xaxis_title=f"{granularity} (Final Status Date)", yaxis_title="%",
                    height=300, margin=dict(l=50, r=50, t=50, b=50), showlegend=False, hovermode='x unified')
                st.plotly_chart(fig_dmg, use_container_width=True)
except:
    st.info("Lost & Damaged data unavailable")

st.divider()

# ============================================================================
# SECTION 6: ANOMALY DETECTION
# ============================================================================

st.markdown("## 6️⃣ Anomaly Detection")

tab1, tab2, tab3 = st.tabs(["Potential Fake Attempts", "Theft & Tampering", "SLA Breaches"])

# TAB 1: Potential Fake Attempts
with tab1:
    fake_tab1, fake_tab2 = st.tabs(["Potential Fake Pickup Attempt", "Potential Fake Delivery Attempt"])
    
    with fake_tab1:
        st.subheader("a. Potential Fake Pickup Attempt")
        st.markdown("**Table 1: Geolocation Violations (FM-GEO)**")
        fm_geo = df_filtered[df_filtered['flag_fake_attempt_fm_geolocation'] == 1].copy()
        st.metric("Parcels Flagged (Geolocation)", len(fm_geo))
        if len(fm_geo) > 0:
            cols = [c for c in ['fm_3pl_name', 'tracking_number', 'origin_region', 'seller_id', 'seller_name', 'fm_courier_id', 'origin_geolocation', 'domestic_pickup/sign_in_failure_geolocation', 'flag_fake_attempt_fm_geolocation'] if c in fm_geo.columns]
            st.dataframe(fm_geo[cols], use_container_width=True, height=300)
        else:
            st.info("✅ No geolocation violations detected")
        st.divider()
        st.markdown("**Table 2: Courier Failure Rate Analysis (EOD)**")
        # Debug: Check if column exists and has data
        if 'fm_eod_failure_rate_pct' in df_filtered.columns:
            fm_eod_count = df_filtered['fm_eod_failure_rate_pct'].notna().sum()
            st.caption(f"*EOD data: {fm_eod_count} records found*")
            if fm_eod_count > 0:
                fm_eod_data = df_filtered[df_filtered['fm_eod_failure_rate_pct'].notna()]
                fm_eod = fm_eod_data[['fm_3pl_name', 'fm_courier_id', 'fm_activity_day', 'fm_eod_failure_rate_pct', 'fm_failure_tier']].drop_duplicates(subset=['fm_courier_id'])
                st.dataframe(fm_eod.sort_values('fm_eod_failure_rate_pct', ascending=False), use_container_width=True, height=300)
            else:
                st.info("🔄 FM EOD analysis: Ready to compute once failure timestamps are processed")
        else:
            st.info("🔄 FM EOD analysis: Column not found (compute_anomalies may have error)")
    
    with fake_tab2:
        st.subheader("b. Potential Fake Delivery Attempt")
        st.markdown("**Table 1: Geolocation Violations (LM-GEO)**")
        lm_geo = df_filtered[df_filtered['flag_fake_attempt_lm_geolocation'] == 1].copy()
        st.metric("Parcels Flagged (Geolocation)", len(lm_geo))
        if len(lm_geo) > 0:
            cols = [c for c in ['lm_3pl_name', 'tracking_number', 'destination_region', 'lm_courier_id', 'destination_geolocation', 'domestic_1st_attempt_failed_geolocation', 'domestic_reattempts_failed_geolocation', 'domestic_delivery_failed_geolocation', 'fd_flag_fake_attempt_detailed'] if c in lm_geo.columns]
            st.dataframe(lm_geo[cols], use_container_width=True, height=300)
        else:
            st.info("✅ No geolocation violations detected")
        st.divider()
        st.markdown("**Table 2: Courier Failure Rate Analysis (EOD)**")
        # Debug: Check if column exists and has data
        if 'lm_eod_failure_rate_pct' in df_filtered.columns:
            lm_eod_count = df_filtered['lm_eod_failure_rate_pct'].notna().sum()
            st.caption(f"*EOD data: {lm_eod_count} records found*")
            if lm_eod_count > 0:
                lm_eod_data = df_filtered[df_filtered['lm_eod_failure_rate_pct'].notna()]
                lm_eod = lm_eod_data[['fm_3pl_name', 'lm_courier_id', 'lm_activity_day', 'lm_eod_failure_rate_pct', 'lm_failure_tier']].drop_duplicates(subset=['lm_courier_id'])
                st.dataframe(lm_eod.sort_values('lm_eod_failure_rate_pct', ascending=False), use_container_width=True, height=300)
            else:
                st.info("🔄 LM EOD analysis: Ready to compute once failure timestamps are processed")
        else:
            st.info("🔄 LM EOD analysis: Column not found (compute_anomalies may have error)")

# TAB 2: Theft & Tampering
with tab2:
    st.info("Theft & Tampering detection: TBD (Weight variance, ePOD diff, Stagnation)")

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

st.caption("Dashboard v4.0+ | Multi-dimensional filtering | Computed anomaly detection | Trend lines")
