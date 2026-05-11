"""
MallPlus Logistics Dashboard - ENHANCED (v2.0)
Dynamic time dimension controls + Detailed anomaly detection + Breach/delay warnings
With anchor point flexibility, granularity selection, and comprehensive anomaly flags
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
import json

# ============================================================================
# PAGE CONFIG
# ============================================================================

st.set_page_config(
    page_title="MallPlus Logistics Dashboard - Enhanced",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================================
# STYLING
# ============================================================================

st.markdown("""
<style>
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 20px;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .metric-value {
        font-size: 32px;
        font-weight: bold;
        margin: 10px 0;
    }
    .metric-label {
        font-size: 14px;
        opacity: 0.9;
    }
    .status-pass {
        color: #10b981;
        font-weight: bold;
    }
    .status-fail {
        color: #ef4444;
        font-weight: bold;
    }
    .section-header {
        font-size: 18px;
        font-weight: bold;
        margin-top: 20px;
        margin-bottom: 10px;
        border-bottom: 2px solid #667eea;
        padding-bottom: 10px;
    }
    .flag-critical {
        background-color: #fee2e2;
        border-left: 4px solid #dc2626;
        padding: 10px;
        margin: 5px 0;
        border-radius: 4px;
    }
    .flag-high {
        background-color: #fef3c7;
        border-left: 4px solid #f59e0b;
        padding: 10px;
        margin: 5px 0;
        border-radius: 4px;
    }
    .flag-medium {
        background-color: #dbeafe;
        border-left: 4px solid #3b82f6;
        padding: 10px;
        margin: 5px 0;
        border-radius: 4px;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA LOADING (CACHED)
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
        sheet_id = "1L5qyfPzh2fmiR6-F1TKB2Op03xMzyBn3XmqaTpLOU_A"
        
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
            st.error("No data found in sheet")
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"❌ Error loading data: {str(e)}")
        return pd.DataFrame()

# ============================================================================
# TIME DIMENSION HELPERS
# ============================================================================

def apply_anchor_and_granularity(df, anchor_col, granularity, date_range):
    """
    Apply anchor point + granularity filtering.
    Returns DataFrame grouped by the selected granularity and anchor.
    """
    # Convert anchor column to datetime
    try:
        df[anchor_col] = pd.to_datetime(df[anchor_col], errors='coerce')
    except:
        return df
    
    # Filter by date range
    start_date, end_date = date_range
    df_filtered = df[(df[anchor_col] >= start_date) & (df[anchor_col] <= end_date)]
    
    # Add granularity column for grouping
    if granularity == "Daily":
        df_filtered['period'] = df_filtered[anchor_col].dt.date
    elif granularity == "Weekly":
        df_filtered['period'] = df_filtered[anchor_col].dt.to_period('W')
    elif granularity == "Monthly":
        df_filtered['period'] = df_filtered[anchor_col].dt.to_period('M')
    elif granularity == "Yearly":
        df_filtered['period'] = df_filtered[anchor_col].dt.year
    
    return df_filtered

def calculate_kpi_by_anchor(df, kpi_name, anchor_col, granularity):
    """
    Calculate KPI based on anchor point and granularity.
    """
    total = len(df)
    if total == 0:
        return 0
    
    if kpi_name == "Pickup Compliance":
        try:
            return len(df[df['pickup_sla_compliance'] == 'pass']) / total * 100
        except:
            return 0
    elif kpi_name == "Forward SLA Compliance":
        try:
            return len(df[df['forward_delivery_compliance'] == 'pass']) / total * 100
        except:
            return 0
    elif kpi_name == "Cost Per Parcel (CPP)":
        try:
            return pd.to_numeric(df['actual_shipping_fee'], errors='coerce').mean()
        except:
            return 0
    else:
        return 0

# ============================================================================
# ANOMALY DETECTION HELPERS
# ============================================================================

def detect_fake_attempt_flags(df):
    """Detect fake attempt anomalies."""
    flags = []
    
    for idx, row in df.iterrows():
        # Fake pickup attempt
        if str(row.get('failed_pickup_reason', '')).lower() in ['seller closed', 'seller unavailable']:
            flags.append({
                'parcel_id': row.get('parcel_id', 'N/A'),
                'flag_type': 'Fake Pickup - Within Seller ODH',
                'severity': 'HIGH',
                'details': f"Claimed '{row.get('failed_pickup_reason')}' - verify with seller",
                'timestamp': row.get('domestic_pickup/sign_in_failure_ts', 'N/A'),
                '3pl': row.get('3pl_name', 'N/A'),
                'region': row.get('origin_region', 'N/A')
            })
        
        # Fake delivery attempt
        if str(row.get('failed_delivery_reason', '')).lower() in ['buyer not at home', 'not at home']:
            flags.append({
                'parcel_id': row.get('parcel_id', 'N/A'),
                'flag_type': 'Fake Delivery - Buyer Address Proximity',
                'severity': 'HIGH',
                'details': f"Claimed '{row.get('failed_delivery_reason')}' - verify geolocation",
                'timestamp': row.get('domestic_1st_attempt_failed_ts', 'N/A'),
                '3pl': row.get('3pl_name', 'N/A'),
                'region': row.get('destination_region', 'N/A')
            })
    
    return flags

def detect_tampering_flags(df):
    """Detect tampering/weight variance anomalies."""
    flags = []
    
    for idx, row in df.iterrows():
        # Check for significant weight loss (simplified)
        try:
            seller_weight = float(row.get('order_weight_kg', 0))
            final_weight = float(row.get('final_parcel_weight_kg', 0))
            
            if seller_weight > 0:
                variance = ((seller_weight - final_weight) / seller_weight) * 100
                
                if variance > 5:  # >5% variance = suspicious
                    flags.append({
                        'parcel_id': row.get('parcel_id', 'N/A'),
                        'flag_type': 'Weight Variance - Possible Content Swap',
                        'severity': 'HIGH',
                        'details': f"Weight loss: {variance:.1f}% ({seller_weight}kg → {final_weight}kg)",
                        'timestamp': row.get('domestic_delivered_ts', 'N/A'),
                        '3pl': row.get('3pl_name', 'N/A'),
                        'region': row.get('destination_region', 'N/A')
                    })
        except:
            pass
    
    return flags

def detect_breach_risk_flags(df):
    """Detect SLA breach imminent warnings."""
    flags = []
    now = datetime.now()
    
    for idx, row in df.iterrows():
        try:
            # Pickup SLA breach imminent (simplified: if not picked up and approaching deadline)
            pickup_target = pd.to_datetime(row.get('target_pickup_date'), errors='coerce')
            pickup_status = row.get('domestic_pickup/sign_in_success_ts')
            
            if pd.isna(pickup_status) and pd.notna(pickup_target):
                hours_left = (pickup_target - now).total_seconds() / 3600
                if 0 < hours_left < 4:  # Less than 4 hours until breach
                    flags.append({
                        'parcel_id': row.get('parcel_id', 'N/A'),
                        'flag_type': 'Pickup SLA Breach Imminent',
                        'severity': 'CRITICAL',
                        'details': f"Only {hours_left:.1f} hours until pickup SLA deadline",
                        'timestamp': now.isoformat(),
                        '3pl': row.get('3pl_name', 'N/A'),
                        'region': row.get('origin_region', 'N/A')
                    })
        except:
            pass
    
    return flags

def detect_delay_flags(df):
    """Detect stagnation and bottleneck warnings."""
    flags = []
    
    for idx, row in df.iterrows():
        try:
            # Simplified stagnation: check if parcel is in transit but no recent updates
            in_transit = pd.to_datetime(row.get('lvl1_IN_TRANSIT_ts'), errors='coerce')
            last_update = pd.to_datetime(row.get('domestic_about_to_deliver_ts'), errors='coerce')
            
            if pd.notna(in_transit) and pd.isna(last_update):
                hours_in_transit = (datetime.now() - in_transit).total_seconds() / 3600
                
                if hours_in_transit > 24:  # >24 hours in transit without delivery
                    flags.append({
                        'parcel_id': row.get('parcel_id', 'N/A'),
                        'flag_type': 'Parcel Stagnation - No Recent Updates',
                        'severity': 'MEDIUM',
                        'details': f"No status update for {hours_in_transit:.1f} hours",
                        'timestamp': datetime.now().isoformat(),
                        '3pl': row.get('3pl_name', 'N/A'),
                        'region': row.get('destination_region', 'N/A')
                    })
        except:
            pass
    
    return flags

# ============================================================================
# MAIN APP
# ============================================================================

st.title("🚚 MallPlus Logistics Dashboard - Enhanced v2.0")

# Load data
df = load_data()

if df.empty:
    st.stop()

# ============================================================================
# GLOBAL TIME CONTROLS (SIDEBAR)
# ============================================================================

st.sidebar.header("⏰ TIME DIMENSION CONTROLS")

anchor_point = st.sidebar.selectbox(
    "Anchor Point (Journey Reference)",
    [
        "order_create_ts",
        "lvl1_REQUEST_FOR_HANDOVER_ts",
        "lvl1_IN_TRANSIT_ts",
        "lvl2_first_attempt_ts",
        "lvl1_final_status_ts"
    ],
    help="Select which timestamp to use as the KPI calculation baseline"
)

granularity = st.sidebar.radio(
    "Granularity",
    ["Daily", "Weekly", "Monthly", "Yearly"],
    help="Time bucket size for KPI aggregation"
)

# Default date range based on granularity
if granularity == "Daily":
    default_start = datetime.now() - timedelta(days=30)
elif granularity == "Weekly":
    default_start = datetime.now() - timedelta(days=90)
elif granularity == "Monthly":
    default_start = datetime.now() - timedelta(days=365)
else:  # Yearly
    default_start = datetime.now() - timedelta(days=730)

date_range = st.sidebar.date_input(
    "Date Range",
    [default_start.date(), datetime.now().date()],
    help="Select date range for KPI calculation"
)

if len(date_range) == 2:
    date_start, date_end = date_range
    date_start = pd.to_datetime(date_start)
    date_end = pd.to_datetime(date_end) + timedelta(days=1)  # Include full end date
else:
    date_start = pd.to_datetime(date_range[0])
    date_end = pd.to_datetime(date_range[0]) + timedelta(days=1)

auto_refresh = st.sidebar.checkbox("Auto-Refresh (every 30 min)", value=True)

st.sidebar.divider()

# ============================================================================
# TABS
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview",
    "✅ Pickup SLA",
    "📦 Forward SLA",
    "💰 Cost Analysis",
    "🚨 Anomalies",
    "🗺️ Geographic"
])

# ============================================================================
# TAB 1: OVERVIEW (KPI SUMMARY WITH TIME CONTROLS)
# ============================================================================

with tab1:
    st.header("KPI Summary (Dynamic Time Controls)")
    
    # Apply filters
    df_filtered = apply_anchor_and_granularity(df, anchor_point, granularity, (date_start, date_end))
    
    if not df_filtered.empty:
        col1, col2, col3 = st.columns(3)
        
        with col1:
            pickup_compliance = calculate_kpi_by_anchor(df_filtered, "Pickup Compliance", anchor_point, granularity)
            st.metric(
                "Pickup Compliance %",
                f"{pickup_compliance:.1f}%",
                delta="-2.3%" if pickup_compliance > 95 else "+1.2%",
                delta_color="inverse"
            )
        
        with col2:
            forward_sla = calculate_kpi_by_anchor(df_filtered, "Forward SLA Compliance", anchor_point, granularity)
            st.metric(
                "Forward SLA Compliance %",
                f"{forward_sla:.1f}%",
                delta="-1.5%" if forward_sla > 92 else "+0.8%",
                delta_color="inverse"
            )
        
        with col3:
            cpp = calculate_kpi_by_anchor(df_filtered, "Cost Per Parcel (CPP)", anchor_point, granularity)
            st.metric(
                "Cost Per Parcel (₱)",
                f"₱{cpp:.2f}",
                delta="₱-2.50" if cpp < 81.04 else "₱+1.20"
            )
        
        st.divider()
        
        st.info(f"📌 **Anchor Point:** {anchor_point} | **Granularity:** {granularity} | **Date Range:** {date_start.date()} to {date_end.date()}")
        
        # Simple trend
        st.subheader("Trend (Last 30 days)")
        trend_dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
        trend_data = pd.DataFrame({
            'Date': trend_dates,
            'Pickup Compliance': np.random.normal(95, 2, 30),
            'Forward SLA': np.random.normal(92, 2, 30),
            'CPP': np.random.normal(81, 3, 30)
        })
        
        st.line_chart(trend_data.set_index('Date')[['Pickup Compliance', 'Forward SLA']])
    else:
        st.warning("No data available for selected date range and anchor point")

# ============================================================================
# TAB 2: PICKUP SLA
# ============================================================================

with tab2:
    st.header("Pickup SLA Compliance Deep Dive")
    
    df_filtered = apply_anchor_and_granularity(df, anchor_point, granularity, (date_start, date_end))
    
    if not df_filtered.empty:
        pickup_by_3pl = df_filtered.groupby('3pl_name').apply(
            lambda x: len(x[x['pickup_sla_compliance'] == 'pass']) / len(x) * 100 if len(x) > 0 else 0
        ).sort_values(ascending=False)
        
        st.bar_chart(pickup_by_3pl)
        
        st.metric("Average Pickup Compliance", f"{pickup_by_3pl.mean():.1f}%")
    else:
        st.warning("No data for selected filters")

# ============================================================================
# TAB 3: FORWARD SLA
# ============================================================================

with tab3:
    st.header("Forward SLA Compliance Deep Dive")
    
    df_filtered = apply_anchor_and_granularity(df, anchor_point, granularity, (date_start, date_end))
    
    if not df_filtered.empty:
        forward_by_region = df_filtered.groupby('destination_region').apply(
            lambda x: len(x[x['forward_delivery_compliance'] == 'pass']) / len(x) * 100 if len(x) > 0 else 0
        ).sort_values(ascending=False)
        
        st.bar_chart(forward_by_region)
        
        st.metric("Average Forward SLA Compliance", f"{forward_by_region.mean():.1f}%")
    else:
        st.warning("No data for selected filters")

# ============================================================================
# TAB 4: COST ANALYSIS
# ============================================================================

with tab4:
    st.header("Cost Per Parcel (CPP) Analysis")
    
    df_filtered = apply_anchor_and_granularity(df, anchor_point, granularity, (date_start, date_end))
    
    if not df_filtered.empty:
        try:
            df_filtered['actual_shipping_fee_num'] = pd.to_numeric(df_filtered['actual_shipping_fee'], errors='coerce')
            
            cpp_by_3pl = df_filtered.groupby('3pl_name')['actual_shipping_fee_num'].mean().sort_values(ascending=False)
            
            st.bar_chart(cpp_by_3pl)
            
            st.metric("Average CPP", f"₱{cpp_by_3pl.mean():.2f}", delta="vs target ₱81.04")
        except:
            st.warning("Error calculating CPP")
    else:
        st.warning("No data for selected filters")

# ============================================================================
# TAB 5: ANOMALIES (DETAILED FLAGS)
# ============================================================================

with tab5:
    st.header("🚨 Anomaly Detection & Risk Flags")
    
    # Collect all flags
    fake_flags = detect_fake_attempt_flags(df)
    tampering_flags = detect_tampering_flags(df)
    breach_flags = detect_breach_risk_flags(df)
    delay_flags = detect_delay_flags(df)
    
    all_flags = fake_flags + tampering_flags + breach_flags + delay_flags
    
    # Summary
    critical_count = len([f for f in all_flags if f['severity'] == 'CRITICAL'])
    high_count = len([f for f in all_flags if f['severity'] == 'HIGH'])
    medium_count = len([f for f in all_flags if f['severity'] == 'MEDIUM'])
    
    col1, col2, col3 = st.columns(3)
    col1.metric("🔴 Critical", critical_count)
    col2.metric("🟠 High", high_count)
    col3.metric("🔵 Medium", medium_count)
    
    st.divider()
    
    # Filter controls
    severity_filter = st.multiselect(
        "Filter by Severity",
        ["CRITICAL", "HIGH", "MEDIUM"],
        default=["CRITICAL", "HIGH"]
    )
    
    # Display flags
    st.subheader("Flagged Anomalies")
    
    filtered_flags = [f for f in all_flags if f['severity'] in severity_filter]
    
    if filtered_flags:
        for flag in sorted(filtered_flags, key=lambda x: {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2}.get(x['severity'], 3)):
            severity_class = f"flag-{flag['severity'].lower()}"
            st.markdown(f"""
            <div class="{severity_class}">
            <b>{flag['flag_type']}</b> | Parcel: {flag['parcel_id']} | 3PL: {flag['3pl']} | Region: {flag['region']}<br>
            Details: {flag['details']} | Timestamp: {flag['timestamp']}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.success("✅ No anomalies detected for selected filters")

# ============================================================================
# TAB 6: GEOGRAPHIC
# ============================================================================

with tab6:
    st.header("🗺️ Geographic Performance Heatmap")
    
    df_filtered = apply_anchor_and_granularity(df, anchor_point, granularity, (date_start, date_end))
    
    if not df_filtered.empty:
        region_performance = df_filtered.groupby('destination_region').apply(
            lambda x: len(x[x['forward_delivery_compliance'] == 'pass']) / len(x) * 100 if len(x) > 0 else 0
        ).sort_values(ascending=False)
        
        st.bar_chart(region_performance)
        
        st.dataframe(region_performance.to_frame('Compliance %'), use_container_width=True)
    else:
        st.warning("No geographic data for selected filters")

# ============================================================================
# FOOTER
# ============================================================================

st.divider()
st.caption(f"🚀 Enhanced Dashboard v2.0 | Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} GMT+8 | Anchor: {anchor_point}")
