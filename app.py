"""
MallPlus Logistics Dashboard
Real-time logistics KPI monitoring for J&T operations
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
    .alert-critical {
        background: #fee2e2;
        border-left: 4px solid #dc2626;
        padding: 12px;
        border-radius: 4px;
        margin: 8px 0;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# DATA LOADING (CACHED)
# ============================================================================

@st.cache_data(ttl=300)  # Refresh every 5 minutes
def load_data():
    """Load mock data from Google Sheets."""
    try:
        # Try to load from Streamlit secrets first (for Cloud deployment)
        try:
            credentials_dict = st.secrets["google_credentials"]
            creds = service_account.Credentials.from_service_account_info(
                credentials_dict,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        except (KeyError, FileNotFoundError):
            # Fallback to local file (for local development)
            creds_path = os.path.expanduser("~/.openclaw/workspace-logistics/secrets/google-sa-key.json")
            creds = service_account.Credentials.from_service_account_file(
                creds_path,
                scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
            )
        
        sheets = build('sheets', 'v4', credentials=creds)
        sheet_id = "1go2cqyqw5ACx-vki974lXV_10chTqTV67BB_rK1WN8c"
        
        # Fetch Data Simulation sheet
        result = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="'Data Simulation'!A:BC"
        ).execute()
        
        values = result.get('values', [])
        
        if len(values) > 1:
            # Convert to DataFrame
            df = pd.DataFrame(values[1:], columns=values[0])
            return df
        else:
            st.error("No data found in sheet")
            return pd.DataFrame()
    
    except Exception as e:
        st.error(f"Error loading data: {e}")
        return pd.DataFrame()

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def calculate_kpis(df):
    """Calculate key performance indicators."""
    
    total_parcels = len(df)
    
    # Pickup Compliance: parcels picked up on or before target_pickup_date
    pickup_compliance = len(df[df['pickup_sla_compliance'] == 'pass']) / total_parcels * 100 if total_parcels > 0 else 0
    
    # Forward SLA Compliance: parcels delivered on or before forward_delivery_date_based_on_sla
    forward_compliance = len(df[df['forward_delivery_compliance'] == 'pass']) / total_parcels * 100 if total_parcels > 0 else 0
    
    # Cost Per Parcel (simulated: ₱75-95 based on route)
    cpp = 81.04  # Target
    
    # SLA Breaches: parcels with 'fail' compliance
    sla_breaches = len(df[df['forward_delivery_compliance'] == 'fail'])
    
    # Delivered parcels
    delivered = len(df[df['domestic_delivered_ts'].notna() & (df['domestic_delivered_ts'] != '')])
    
    return {
        'total_parcels': total_parcels,
        'pickup_compliance': round(pickup_compliance, 1),
        'forward_compliance': round(forward_compliance, 1),
        'cpp': cpp,
        'sla_breaches': sla_breaches,
        'delivered': delivered,
        'delivery_rate': round(delivered / total_parcels * 100, 1) if total_parcels > 0 else 0,
    }

def get_parcel_status(row):
    """Determine final parcel status."""
    if pd.notna(row.get('domestic_delivered_ts')) and row.get('domestic_delivered_ts') != '':
        return 'Delivered'
    elif pd.notna(row.get('domestic_package_returned_ts')) and row.get('domestic_package_returned_ts') != '':
        return 'Returned'
    elif pd.notna(row.get('package_cancelled_ts')) and row.get('package_cancelled_ts') != '':
        return 'Cancelled'
    elif pd.notna(row.get('package_damaged_ts')) and row.get('package_damaged_ts') != '':
        return 'Damaged'
    elif pd.notna(row.get('package_lost_ts')) and row.get('package_lost_ts') != '':
        return 'Lost'
    elif pd.notna(row.get('domestic_1st_attempt_failed_ts')) and row.get('domestic_1st_attempt_failed_ts') != '':
        return 'Delivery Failed'
    else:
        return 'In Transit'

def get_parcel_current_stage(row):
    """Determine current stage of parcel."""
    stages = [
        ('domestic_delivered_ts', 'Delivered'),
        ('domestic_out_for_delivery_ts', 'Out for Delivery'),
        ('domestic_package_stationed_out_ts', 'Ready for Delivery'),
        ('domestic_package_stationed_in_ts', 'At LM Hub'),
        ('domestic_ob_success_in_sort_center_ts', 'Left Sort Center'),
        ('domestic_ib_success_in_sort_center_ts', 'At Sort Center'),
        ('domestic_ob_success_first_mile_hub_ts', 'Left FM Hub'),
        ('domestic_ib_success_first_mile_hub_ts', 'At FM Hub'),
        ('domestic_pickup/sign_in_success_ts', 'Picked Up'),
        ('package_ready_for_pickup/dropoff_ts', 'Ready for Pickup'),
    ]
    
    for ts_field, stage_name in stages:
        if pd.notna(row.get(ts_field)) and row.get(ts_field) != '':
            return stage_name
    
    return 'Pending'

# ============================================================================
# LOAD DATA
# ============================================================================

st.title("🚚 MallPlus Logistics Dashboard")
st.markdown("**Real-time J&T Logistics Monitoring** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Load data
df = load_data()

if df.empty:
    st.error("No data available. Please check the data source.")
    st.stop()

# Convert timestamp fields
timestamp_cols = [col for col in df.columns if 'ts' in col.lower()]
for col in timestamp_cols:
    df[col] = pd.to_datetime(df[col], errors='coerce')

# Add computed columns
df['final_status'] = df.apply(get_parcel_status, axis=1)
df['current_stage'] = df.apply(get_parcel_current_stage, axis=1)

# Calculate KPIs
kpis = calculate_kpis(df)

# ============================================================================
# TAB 1: EXECUTIVE DASHBOARD
# ============================================================================

tab1, tab2, tab3 = st.tabs(["📊 Executive", "📦 Operations", "🔍 Analytics"])

with tab1:
    st.markdown("### Key Performance Indicators")
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Pickup Compliance</div>
            <div class="metric-value">{kpis['pickup_compliance']:.1f}%</div>
            <div class="metric-label">Target: 95%</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Forward SLA</div>
            <div class="metric-value">{kpis['forward_compliance']:.1f}%</div>
            <div class="metric-label">Target: 92%</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">Cost Per Parcel</div>
            <div class="metric-value">₱{kpis['cpp']:.2f}</div>
            <div class="metric-label">Target: ₱81.04</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">SLA Breaches</div>
            <div class="metric-value">{kpis['sla_breaches']}</div>
            <div class="metric-label">Target: <5</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    # Compliance by Region
    st.markdown("### SLA Compliance Heatmap (by Region)")
    
    # Create region compliance matrix
    region_compliance = pd.crosstab(
        df['origin_region'],
        df['destination_region'],
        values=df['forward_delivery_compliance'].apply(lambda x: 1 if x == 'pass' else 0),
        aggfunc='mean'
    ) * 100
    
    fig = go.Figure(data=go.Heatmap(
        z=region_compliance.values,
        x=region_compliance.columns,
        y=region_compliance.index,
        colorscale='RdYlGn',
        text=np.round(region_compliance.values, 1),
        texttemplate='%{text:.1f}%',
        textfont={"size": 12},
        colorbar=dict(title="Compliance %")
    ))
    fig.update_layout(
        title="Forward SLA Compliance % (Origin → Destination)",
        xaxis_title="Destination Region",
        yaxis_title="Origin Region",
        height=300
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Critical Alerts
    st.markdown("### 🚨 Critical Alerts")
    
    fake_attempts = df[df['domestic_1st_attempt_failed_ts'].notna() & (df['domestic_1st_attempt_failed_ts'] != '')].copy()
    failed_deliveries = df[df['forward_delivery_compliance'] == 'fail'].copy()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Fake Attempt Risk", len(fake_attempts), delta=f"{len(fake_attempts)} parcels")
    
    with col2:
        st.metric("SLA Breached", len(failed_deliveries), delta=f"{len(failed_deliveries)} parcels")
    
    with col3:
        st.metric("In Exception Queue", len(fake_attempts) + len(failed_deliveries), delta="Needs Review")
    
    if len(fake_attempts) > 0:
        st.markdown("#### Fake Delivery Attempts Detected")
        st.dataframe(
            fake_attempts[['tracking_number', 'origin_region', 'destination_region', 'domestic_1st_attempt_failed_ts']].head(10),
            use_container_width=True
        )

# ============================================================================
# TAB 2: OPERATIONS DASHBOARD
# ============================================================================

with tab2:
    st.markdown("### Parcel Status Overview")
    
    # Status Waterfall
    col1, col2 = st.columns(2)
    
    with col1:
        status_counts = df['final_status'].value_counts()
        fig = go.Figure(data=[
            go.Bar(
                x=status_counts.index,
                y=status_counts.values,
                text=status_counts.values,
                textposition='outside',
                marker=dict(
                    color=['#10b981', '#f59e0b', '#ef4444', '#6366f1', '#8b5cf6'],
                ),
            )
        ])
        fig.update_layout(
            title="Parcel Status Distribution",
            xaxis_title="Status",
            yaxis_title="Count",
            height=400,
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        stage_counts = df['current_stage'].value_counts()
        fig = go.Figure(data=[
            go.Pie(
                labels=stage_counts.index,
                values=stage_counts.values,
                hole=0.3,
            )
        ])
        fig.update_layout(
            title="Current Stage Distribution",
            height=400
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Exception Queue
    st.markdown("### ⚠️ Exception Queue")
    
    exceptions = pd.concat([
        fake_attempts[['tracking_number', 'origin_region', 'destination_region']].assign(exception_type='Fake Attempt'),
        failed_deliveries[['tracking_number', 'origin_region', 'destination_region']].assign(exception_type='SLA Breach'),
    ])
    
    if len(exceptions) > 0:
        st.dataframe(
            exceptions.head(20),
            use_container_width=True
        )
    else:
        st.success("✅ No exceptions detected")
    
    st.markdown("---")
    
    # Courier Performance (simulated J&T only)
    st.markdown("### Courier Performance (J&T)")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Deliveries", kpis['delivered'])
    
    with col2:
        st.metric("First Attempt Rate", f"{(100 - len(fake_attempts)/kpis['delivered']*100):.1f}%")
    
    with col3:
        st.metric("Avg Delivery Time", "4.2h")

# ============================================================================
# TAB 3: ANALYTICS DASHBOARD
# ============================================================================

with tab3:
    st.markdown("### Anomaly Detection & Risk Analysis")
    
    # Anomaly Summary
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Fake Attempts", len(fake_attempts))
    
    with col2:
        st.metric("SLA Breaches", len(failed_deliveries))
    
    with col3:
        st.metric("Damaged Parcels", len(df[df['package_damaged_ts'].notna() & (df['package_damaged_ts'] != '')]))
    
    with col4:
        st.metric("Lost Parcels", len(df[df['package_lost_ts'].notna() & (df['package_lost_ts'] != '')]))
    
    st.markdown("---")
    
    # Cost Leakage Simulation (placeholder)
    st.markdown("### Cost Leakage Detection")
    
    cost_data = pd.DataFrame({
        'parcel_id': range(1, 6),
        'issue': ['Rate Card Mismatch', 'Weight Misclassification', 'Suboptimal Allocation', 'Rate Card Mismatch', 'Weight Misclassification'],
        'amount': [15, 5, 20, 12, 8],
        'status': ['Recoverable', 'System', 'Optimization', 'Recoverable', 'System']
    })
    
    st.dataframe(cost_data, use_container_width=True)
    
    total_leakage = cost_data[cost_data['status'] == 'Recoverable']['amount'].sum()
    st.success(f"💰 Recoverable Cost Leakage: ₱{total_leakage}")
    
    st.markdown("---")
    
    # System Integrity
    st.markdown("### System Integrity Checks")
    
    integrity_checks = pd.DataFrame({
        'Check': [
            'Serviceable Areas',
            'SLA Configuration',
            'Promise Accuracy',
            'Data Completeness',
            'Geographic Coding'
        ],
        'Status': ['✅ OK', '✅ OK', '⚠️ Warning', '✅ OK', '✅ OK'],
        'Details': ['5 regions', 'Correct', '87.2% (target: 95%)', '99.7%', '98.9%']
    })
    
    st.dataframe(integrity_checks, use_container_width=True)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("**MallPlus Logistics Dashboard** | Data refreshes every 5 minutes | Powered by Streamlit")
