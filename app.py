"""
MallPlus Logistics Dashboard - Full Redesign
Real-time logistics KPI monitoring for J&T operations
140-field schema with seller, cost, and geographic analytics
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
        creds_path = os.path.expanduser("~/.openclaw/workspace-logistics/secrets/google-sa-key.json")
        creds = service_account.Credentials.from_service_account_file(
            creds_path,
            scopes=['https://www.googleapis.com/auth/spreadsheets.readonly']
        )
        
        sheets = build('sheets', 'v4', credentials=creds)
        sheet_id = "1L5qyfPzh2fmiR6-F1TKB2Op03xMzyBn3XmqaTpLOU_A"
        
        # Fetch Simulated Data sheet
        result = sheets.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range="'Simulated Data'!A:EJ"
        ).execute()
        
        values = result.get('values', [])
        
        if len(values) > 1:
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
    total = len(df)
    
    pickup_compliance = len(df[df['pickup_sla_compliance'] == 'pass']) / total * 100 if total > 0 else 0
    forward_compliance = len(df[df['forward_delivery_compliance'] == 'pass']) / total * 100 if total > 0 else 0
    
    try:
        avg_shipping_fee = pd.to_numeric(df['actual_shipping_fee'], errors='coerce').mean()
    except:
        avg_shipping_fee = 0
    
    sla_breaches = len(df[df['forward_delivery_compliance'] == 'fail'])
    delivered = len(df[df['final_status'] == 'DELIVERED'])
    
    return {
        'total_parcels': total,
        'pickup_compliance': round(pickup_compliance, 1),
        'forward_compliance': round(forward_compliance, 1),
        'avg_shipping_fee': round(avg_shipping_fee, 2),
        'cpp_target': 81.04,
        'sla_breaches': sla_breaches,
        'delivered': delivered,
        'delivery_rate': round(delivered / total * 100, 1) if total > 0 else 0,
    }

def get_status_distribution(df):
    """Get parcel status breakdown."""
    return df['final_status'].value_counts()

def get_category_performance(df):
    """Get performance by seller category."""
    category_stats = df.groupby('seller_category').agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'actual_shipping_fee': 'mean'
    }).round(2)
    
    category_stats.columns = ['Parcel Count', 'Forward SLA %', 'Avg Fee (₱)']
    return category_stats

def get_region_performance(df):
    """Get performance by origin region."""
    region_stats = df.groupby('origin_region').agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'pickup_sla_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'actual_shipping_fee': 'mean'
    }).round(2)
    
    region_stats.columns = ['Parcel Count', 'Forward SLA %', 'Pickup SLA %', 'Avg Fee (₱)']
    return region_stats

def get_delivery_option_performance(df):
    """Get performance by delivery option."""
    delivery_stats = df.groupby('delivery_option').agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0,
        'actual_shipping_fee': 'mean'
    }).round(2)
    
    delivery_stats.columns = ['Parcel Count', 'Forward SLA %', 'Avg Fee (₱)']
    return delivery_stats

def get_payment_distribution(df):
    """Get payment type distribution."""
    return df['payment_type'].value_counts()

def get_cost_analysis(df):
    """Get cost analysis by region and category."""
    cost_by_region = df.groupby('origin_region')['actual_shipping_fee'].agg(['count', 'mean', 'sum']).round(2)
    cost_by_region.columns = ['Parcels', 'Avg Fee (₱)', 'Total Cost (₱)']
    return cost_by_region

# ============================================================================
# MAIN APP
# ============================================================================

st.title("🚚 MallPlus Logistics Dashboard - Full Analytics")
st.markdown("**Real-time J&T Logistics Monitoring** | 500 Parcels | April 1-7, 2026 | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))

# Load data
df = load_data()

if df.empty:
    st.error("No data available. Please check the data source.")
    st.stop()

# Convert timestamp columns
timestamp_cols = [col for col in df.columns if 'ts' in col.lower()]
for col in timestamp_cols:
    df[col] = pd.to_datetime(df[col], errors='coerce')

# Calculate KPIs
kpis = calculate_kpis(df)

# ============================================================================
# TABS
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Executive", 
    "📦 Operations", 
    "🔍 Analytics",
    "🏪 Seller Performance",
    "💰 Cost Analysis",
    "🌍 Geographic Heatmap"
])

# ============================================================================
# TAB 1: EXECUTIVE DASHBOARD
# ============================================================================

with tab1:
    st.markdown("### Key Performance Indicators")
    
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
            <div class="metric-label">Avg Shipping Fee</div>
            <div class="metric-value">₱{kpis['avg_shipping_fee']:.2f}</div>
            <div class="metric-label">Target CPP: ₱{kpis['cpp_target']}</div>
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
    
    # Status Distribution
    st.markdown("### Parcel Status Distribution")
    status_dist = get_status_distribution(df)
    
    col1, col2 = st.columns(2)
    
    with col1:
        fig = go.Figure(data=[
            go.Bar(
                x=status_dist.index,
                y=status_dist.values,
                text=status_dist.values,
                textposition='outside',
                marker=dict(color=['#10b981', '#f59e0b', '#ef4444', '#6366f1', '#8b5cf6'][:len(status_dist)])
            )
        ])
        fig.update_layout(
            title="Parcel Count by Status",
            xaxis_title="Status",
            yaxis_title="Count",
            height=350,
            showlegend=False
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = go.Figure(data=[
            go.Pie(
                labels=status_dist.index,
                values=status_dist.values,
            )
        ])
        fig.update_layout(title="Status Distribution %", height=350)
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # SLA Compliance Heatmap
    st.markdown("### Forward SLA Compliance by Region")
    
    compliance_matrix = pd.crosstab(
        df['origin_region'],
        df['destination_region'],
        values=(df['forward_delivery_compliance'] == 'pass').astype(int),
        aggfunc='mean'
    ) * 100
    
    fig = go.Figure(data=go.Heatmap(
        z=compliance_matrix.values,
        x=compliance_matrix.columns,
        y=compliance_matrix.index,
        colorscale='RdYlGn',
        text=np.round(compliance_matrix.values, 1),
        texttemplate='%{text:.1f}%',
        textfont={"size": 10},
        colorbar=dict(title="Compliance %")
    ))
    fig.update_layout(
        title="Forward SLA Compliance % (Origin → Destination)",
        xaxis_title="Destination Region",
        yaxis_title="Origin Region",
        height=400
    )
    st.plotly_chart(fig, use_container_width=True)

# ============================================================================
# TAB 2: OPERATIONS DASHBOARD
# ============================================================================

with tab2:
    st.markdown("### Operational Metrics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("Total Parcels", kpis['total_parcels'])
    
    with col2:
        st.metric("Delivered", kpis['delivered'], delta=f"{kpis['delivery_rate']:.1f}%")
    
    with col3:
        st.metric("In Exception Queue", kpis['sla_breaches'])
    
    st.markdown("---")
    
    # Delivery Option Performance
    st.markdown("### Performance by Delivery Option")
    delivery_perf = get_delivery_option_performance(df)
    st.dataframe(delivery_perf, use_container_width=True)
    
    st.markdown("---")
    
    # Payment Type Distribution
    st.markdown("### Payment Type Distribution")
    
    col1, col2 = st.columns(2)
    
    with col1:
        payment_dist = get_payment_distribution(df)
        fig = go.Figure(data=[
            go.Pie(labels=payment_dist.index, values=payment_dist.values)
        ])
        fig.update_layout(title="Payment Type Distribution", height=350)
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        payment_stats = df.groupby('payment_type').agg({
            'tracking_number': 'count',
            'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100
        }).round(2)
        payment_stats.columns = ['Count', 'Forward SLA %']
        st.dataframe(payment_stats, use_container_width=True)

# ============================================================================
# TAB 3: ANALYTICS DASHBOARD
# ============================================================================

with tab3:
    st.markdown("### Anomaly Detection & Risk Analysis")
    
    # Breach Analysis
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        breaches = len(df[df['is_forward_hard_breach'] == 'Yes']) if 'is_forward_hard_breach' in df.columns else 0
        st.metric("Forward Hard Breach", breaches)
    
    with col2:
        rts = len(df[df['final_status'] == 'RETURNED'])
        st.metric("RTS Parcels", rts)
    
    with col3:
        damaged = len(df[df['final_status'] == 'DAMAGED'])
        st.metric("Damaged", damaged)
    
    with col4:
        lost = len(df[df['final_status'] == 'LOST'])
        st.metric("Lost", lost)
    
    st.markdown("---")
    
    # Risk by Category
    st.markdown("### Risk Analysis by Category")
    
    risk_by_category = df.groupby('seller_category').agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'fail').sum() / len(x) * 100,
    }).round(2)
    risk_by_category.columns = ['Parcel Count', 'SLA Breach Rate %']
    
    fig = px.bar(
        risk_by_category.reset_index(),
        x='seller_category',
        y='SLA Breach Rate %',
        title='SLA Breach Rate by Seller Category',
        labels={'seller_category': 'Category', 'SLA Breach Rate %': 'Breach Rate (%)'},
        height=350
    )
    st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Exception Queue
    st.markdown("### Exception Queue (SLA Breaches)")
    
    exceptions = df[df['forward_delivery_compliance'] == 'fail'][['tracking_number', 'seller_category', 'origin_region', 'destination_region', 'final_status']]
    
    if len(exceptions) > 0:
        st.dataframe(exceptions.head(20), use_container_width=True)
    else:
        st.success("✅ No SLA breaches detected")

# ============================================================================
# TAB 4: SELLER PERFORMANCE
# ============================================================================

with tab4:
    st.markdown("### Seller Performance Analysis")
    
    # Category Performance
    st.markdown("#### Performance by Seller Category")
    category_perf = get_category_performance(df)
    st.dataframe(category_perf, use_container_width=True)
    
    st.markdown("---")
    
    # Category Comparison
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.bar(
            category_perf.reset_index(),
            x='seller_category',
            y='Forward SLA %',
            title='Forward SLA Compliance by Category',
            labels={'seller_category': 'Category'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(
            category_perf.reset_index(),
            x='seller_category',
            y='Avg Fee (₱)',
            title='Average Shipping Fee by Category',
            labels={'seller_category': 'Category'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Seller Segment Analysis
    st.markdown("#### Performance by Seller Segment")
    segment_perf = df.groupby('seller_segment').agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100,
        'actual_shipping_fee': 'mean'
    }).round(2)
    segment_perf.columns = ['Parcel Count', 'Forward SLA %', 'Avg Fee (₱)']
    st.dataframe(segment_perf, use_container_width=True)

# ============================================================================
# TAB 5: COST ANALYSIS
# ============================================================================

with tab5:
    st.markdown("### Cost Analysis & Financial Metrics")
    
    # Cost by Region
    st.markdown("#### Cost Breakdown by Origin Region")
    cost_region = get_cost_analysis(df)
    st.dataframe(cost_region, use_container_width=True)
    
    st.markdown("---")
    
    # Cost Trends
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.bar(
            cost_region.reset_index(),
            x='origin_region',
            y='Avg Fee (₱)',
            title='Average Shipping Fee by Region',
            labels={'origin_region': 'Region'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(
            cost_region.reset_index(),
            x='origin_region',
            y='Total Cost (₱)',
            title='Total Cost by Region',
            labels={'origin_region': 'Region'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Cost by Category
    st.markdown("#### Cost by Seller Category")
    cost_category = df.groupby('seller_category').agg({
        'actual_shipping_fee': ['count', 'mean', 'sum']
    }).round(2)
    cost_category.columns = ['Parcel Count', 'Avg Fee (₱)', 'Total Cost (₱)']
    st.dataframe(cost_category, use_container_width=True)
    
    st.markdown("---")
    
    # Summary Metrics
    st.markdown("#### Overall Cost Metrics")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        total_cost = df['actual_shipping_fee'].astype(float).sum()
        st.metric("Total Cost (₱)", f"{total_cost:,.2f}")
    
    with col2:
        avg_cost = df['actual_shipping_fee'].astype(float).mean()
        st.metric("Average Cost (₱)", f"{avg_cost:.2f}")
    
    with col3:
        cost_per_successful = df[df['final_status'] == 'DELIVERED']['actual_shipping_fee'].astype(float).mean()
        st.metric("CPP (Delivered) (₱)", f"{cost_per_successful:.2f}")

# ============================================================================
# TAB 6: GEOGRAPHIC HEATMAP
# ============================================================================

with tab6:
    st.markdown("### Geographic Performance Analysis")
    
    # Region Performance
    st.markdown("#### Region Performance Matrix")
    region_perf = get_region_performance(df)
    st.dataframe(region_perf, use_container_width=True)
    
    st.markdown("---")
    
    # Regional Metrics
    col1, col2 = st.columns(2)
    
    with col1:
        fig = px.bar(
            region_perf.reset_index(),
            x='origin_region',
            y='Forward SLA %',
            title='Forward SLA Compliance by Origin Region',
            labels={'origin_region': 'Region'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    with col2:
        fig = px.bar(
            region_perf.reset_index(),
            x='origin_region',
            y='Pickup SLA %',
            title='Pickup SLA Compliance by Origin Region',
            labels={'origin_region': 'Region'},
            height=350
        )
        st.plotly_chart(fig, use_container_width=True)
    
    st.markdown("---")
    
    # Route Analysis
    st.markdown("#### Top 10 Routes by Volume")
    
    route_analysis = df.groupby(['origin_region', 'destination_region']).agg({
        'tracking_number': 'count',
        'forward_delivery_compliance': lambda x: (x == 'pass').sum() / len(x) * 100
    }).round(2)
    route_analysis.columns = ['Parcel Count', 'Forward SLA %']
    route_analysis = route_analysis.sort_values('Parcel Count', ascending=False).head(10)
    st.dataframe(route_analysis, use_container_width=True)

# ============================================================================
# FOOTER
# ============================================================================

st.markdown("---")
st.markdown("**MallPlus Logistics Dashboard** | 500 Parcels | April 1-7, 2026 | Data refreshes every 5 minutes | Powered by Streamlit")
