"""
MallPlus Logistics Dashboard - Enhanced Layout v2.1
Professional analytics dashboard with monthly OKR table and performance charts
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
# HELPER FUNCTIONS
# ============================================================================

def calculate_kpis(df):
    """Calculate key performance indicators."""
    total = len(df)
    
    try:
        pickup_compliance = len(df[df['pickup_sla_compliance'] == 'pass']) / total * 100 if total > 0 else 0
    except:
        pickup_compliance = 0
    
    try:
        forward_compliance = len(df[df['forward_delivery_compliance'] == 'pass']) / total * 100 if total > 0 else 0
    except:
        forward_compliance = 0
    
    try:
        avg_shipping_fee = pd.to_numeric(df['actual_shipping_fee'], errors='coerce').mean()
    except:
        avg_shipping_fee = 0
    
    try:
        delivered = len(df[df['final_status'] == 'DELIVERED'])
    except:
        delivered = 0
    
    try:
        failed_delivery = len(df[df['final_status'].isin(['FAILED', 'RTS'])])
    except:
        failed_delivery = 0
    
    try:
        rts = len(df[df['final_status'] == 'RTS'])
    except:
        rts = 0
    
    try:
        damaged = len(df[df['final_status'] == 'DAMAGED'])
    except:
        damaged = 0
    
    try:
        lost = len(df[df['final_status'] == 'LOST'])
    except:
        lost = 0
    
    return {
        'total_parcels': total,
        'delivered': delivered,
        'pickup_compliance': round(pickup_compliance, 1),
        'forward_compliance': round(forward_compliance, 1),
        'cpp': round(avg_shipping_fee, 2),
        'failed_delivery_count': failed_delivery,
        'rts_count': rts,
        'damaged_count': damaged,
        'lost_count': lost,
        'failed_delivery_pct': round(failed_delivery / total * 100, 1) if total > 0 else 0,
        'rts_pct': round(rts / total * 100, 1) if total > 0 else 0,
        'damaged_pct': round(damaged / total * 100, 1) if total > 0 else 0,
        'lost_pct': round(lost / total * 100, 1) if total > 0 else 0,
    }

def get_monthly_okr_table(df):
    """Get monthly OKR summary table."""
    try:
        df['order_date'] = pd.to_datetime(df['order_create_ts'], errors='coerce')
        df['month'] = df['order_date'].dt.to_period('M')
    except:
        return pd.DataFrame()
    
    monthly_stats = df.groupby('month').agg({
        'tracking_number': 'count',
        'final_status': lambda x: (x == 'DELIVERED').sum(),
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'pickup_sla_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'actual_shipping_fee': 'mean',
        'final_status': lambda x: (x.isin(['FAILED', 'RTS'])).sum() / len(x) * 100,
    }).round(2)
    
    monthly_stats.columns = ['Delivered Volume', 'Forward SLA %', 'Pickup SLA %', 'CPP (₱)', 'Failed Delivery %']
    
    # Recalculate to fix issue
    monthly_stats = df.groupby('month').agg({
        'tracking_number': 'count',
    })
    monthly_stats.columns = ['Total Volume']
    
    delivered = df.groupby('month').apply(lambda x: (x['final_status'] == 'DELIVERED').sum())
    forward_sla = df.groupby('month').apply(lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0)
    pickup_sla = df.groupby('month').apply(lambda x: (x['pickup_sla_compliance'] == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0)
    cpp = df.groupby('month')['actual_shipping_fee'].apply(lambda x: pd.to_numeric(x, errors='coerce').mean())
    failed_pct = df.groupby('month').apply(lambda x: (x['final_status'].isin(['FAILED', 'RTS'])).sum() / len(x) * 100 if len(x) > 0 else 0)
    rts_pct = df.groupby('month').apply(lambda x: (x['final_status'] == 'RTS').sum() / len(x) * 100 if len(x) > 0 else 0)
    
    monthly_stats['Delivered Volume'] = delivered
    monthly_stats['Forward SLA %'] = forward_sla.round(1)
    monthly_stats['Pickup SLA %'] = pickup_sla.round(1)
    monthly_stats['CPP (₱)'] = cpp.round(2)
    monthly_stats['Failed Delivery %'] = failed_pct.round(1)
    monthly_stats['RTS %'] = rts_pct.round(1)
    
    return monthly_stats

# ============================================================================
# MAIN APP
# ============================================================================

st.title("🚚 MallPlus Logistics Dashboard")
st.markdown("**Real-time J&T Logistics Monitoring** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Load data
df = load_data()

if df.empty:
    st.error("❌ No data available.")
    st.stop()

# Convert columns
for col in df.columns:
    if 'ts' in col.lower():
        try:
            df[col] = pd.to_datetime(df[col], errors='coerce')
        except:
            pass
    elif col in ['package_weight', 'actual_shipping_fee', 'estimated_shipping_fee']:
        try:
            df[col] = pd.to_numeric(df[col], errors='coerce')
        except:
            pass

kpis = calculate_kpis(df)

# ============================================================================
# FILTER ROW
# ============================================================================

st.markdown("### 📊 Filters & Time Dimension")

col1, col2, col3, col4 = st.columns(4)

with col1:
    venture = st.selectbox("3PL Partner", df['3pl_name'].unique() if '3pl_name' in df.columns else ['J&T'])

with col2:
    date_range = st.date_input("Date Range", [datetime.now() - timedelta(days=30), datetime.now()])

with col3:
    granularity = st.radio("Time Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True)

with col4:
    st.empty()

st.divider()

# Filter data by venture
df_filtered = df[df['3pl_name'] == venture] if '3pl_name' in df.columns else df

# ============================================================================
# MONTHLY OKR TABLE
# ============================================================================

st.markdown("### 📈 Monthly OKR Summary")

monthly_table = get_monthly_okr_table(df_filtered)

if not monthly_table.empty:
    st.dataframe(monthly_table, width="stretch", use_container_width=True)
else:
    st.info("No monthly data available")

st.divider()

# ============================================================================
# CHARTS - ROW 1
# ============================================================================

st.markdown("### 📉 Performance Charts")

col1, col2 = st.columns(2)

with col1:
    # Delivery Volume Trend
    try:
        df_filtered['order_date'] = pd.to_datetime(df_filtered['order_create_ts'], errors='coerce')
        daily_volume = df_filtered.groupby(df_filtered['order_date'].dt.date).size()
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_volume.index, y=daily_volume.values, mode='lines+markers', name='Actual'))
        fig.add_hline(y=daily_volume.mean(), line_dash="dash", line_color="red", annotation_text="Target")
        fig.update_layout(title="Delivery Volume Trend", xaxis_title="Date", yaxis_title="Volume", height=350)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("Volume data unavailable")

with col2:
    # Forward SLA Compliance Trend
    try:
        daily_sla = df_filtered.groupby(df_filtered['order_date'].dt.date).apply(
            lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100
        )
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_sla.index, y=daily_sla.values, mode='lines+markers', name='Actual'))
        fig.add_hline(y=92, line_dash="dash", line_color="red", annotation_text="Target (92%)")
        fig.update_layout(title="Forward SLA Compliance %", xaxis_title="Date", yaxis_title="Compliance %", height=350)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("SLA data unavailable")

# ============================================================================
# CHARTS - ROW 2
# ============================================================================

col1, col2 = st.columns(2)

with col1:
    # Pickup Compliance Trend
    try:
        daily_pickup = df_filtered.groupby(df_filtered['order_date'].dt.date).apply(
            lambda x: (x['pickup_sla_compliance'] == 'pass').sum() / len(x) * 100
        )
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_pickup.index, y=daily_pickup.values, mode='lines+markers', name='Actual'))
        fig.add_hline(y=95, line_dash="dash", line_color="red", annotation_text="Target (95%)")
        fig.update_layout(title="Pickup Compliance %", xaxis_title="Date", yaxis_title="Compliance %", height=350)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("Pickup data unavailable")

with col2:
    # CPP Trend
    try:
        daily_cpp = df_filtered.groupby(df_filtered['order_date'].dt.date)['actual_shipping_fee'].apply(
            lambda x: pd.to_numeric(x, errors='coerce').mean()
        )
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_cpp.index, y=daily_cpp.values, mode='lines+markers', name='Actual'))
        fig.add_hline(y=81.04, line_dash="dash", line_color="red", annotation_text="Target (₱81.04)")
        fig.update_layout(title="Cost Per Parcel (CPP)", xaxis_title="Date", yaxis_title="Cost (₱)", height=350)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("Cost data unavailable")

st.divider()

# ============================================================================
# CHARTS - ROW 3
# ============================================================================

col1, col2 = st.columns(2)

with col1:
    # Failed Delivery %
    try:
        daily_fd = df_filtered.groupby(df_filtered['order_date'].dt.date).apply(
            lambda x: (x['final_status'].isin(['FAILED', 'RTS'])).sum() / len(x) * 100
        )
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=daily_fd.index, y=daily_fd.values, mode='lines+markers', name='Actual', line=dict(color='#ef4444')))
        fig.add_hline(y=5, line_dash="dash", line_color="orange", annotation_text="Target (5%)")
        fig.update_layout(title="Failed Delivery %", xaxis_title="Date", yaxis_title="FD %", height=350)
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("FD data unavailable")

with col2:
    # Regional Performance
    try:
        region_perf = df_filtered.groupby('destination_region').apply(
            lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100
        ).sort_values(ascending=False)
        
        fig = px.bar(
            x=region_perf.index,
            y=region_perf.values,
            title="Forward SLA by Region",
            labels={'x': 'Region', 'y': 'Compliance %'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    except:
        st.info("Regional data unavailable")

st.divider()

# ============================================================================
# SUMMARY METRICS
# ============================================================================

st.markdown("### 📊 Current Period Summary")

col1, col2, col3, col4, col5 = st.columns(5)

with col1:
    st.metric("Total Parcels", kpis['total_parcels'])

with col2:
    st.metric("Delivered", kpis['delivered'])

with col3:
    st.metric("Forward SLA", f"{kpis['forward_compliance']}%")

with col4:
    st.metric("Pickup SLA", f"{kpis['pickup_compliance']}%")

with col5:
    st.metric("CPP", f"₱{kpis['cpp']:.2f}")

st.caption(f"Dashboard version 2.1 | Last refresh: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
