"""
MallPlus Logistics Dashboard - Phase 2: Multi-Tab Architecture & Advanced Analytics v3.1
Refactored from single-page to 6-tab structure with Phase 2 features:
- Tab 1: EXECUTIVE (KPI summary + trends)
- Tab 2: OPERATIONS (Courier Scorecard + Route Matrix + Breach Prediction)
- Tab 3: COST (3PL Comparative Analysis)
- Tab 4: PERFORMANCE (Compliance & Lost/Damaged trends)
- Tab 5: EXCEPTIONS (Prioritized anomaly queue)
- Tab 6: FORECASTING (Placeholder for Phase 3)
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
    page_title="MallPlus Logistics Dashboard - Phase 2",
    page_icon="🚚",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("🚚 MallPlus Logistics Dashboard v3.1")
st.markdown("**Multi-Tab Analytics | Phase 2 Implementation** | Last Updated: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8") + " | Ready ✅")

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
        
        # LM Geolocation: >1km from destination
        df['flag_fake_attempt_lm_geolocation'] = 0
        df['fd_flag_fake_attempt_detailed'] = None
        
        if 'destination_geolocation' in df.columns:
            for idx in range(len(df)):
                d = parse_geo(df.iloc[idx]['destination_geolocation'])
                if not d:
                    continue
                
                flags = []
                if 'domestic_1st_attempt_failed_geolocation' in df.columns:
                    f1 = parse_geo(df.iloc[idx]['domestic_1st_attempt_failed_geolocation'])
                    if f1 and haversine(d[1], d[0], f1[1], f1[0]) >= 1.0:
                        flags.append('1st Attempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
                if 'domestic_reattempts_failed_geolocation' in df.columns:
                    fr = parse_geo(df.iloc[idx]['domestic_reattempts_failed_geolocation'])
                    if fr and haversine(d[1], d[0], fr[1], fr[0]) >= 1.0:
                        flags.append('Reattempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
                if 'domestic_delivery_failed_geolocation' in df.columns:
                    ff = parse_geo(df.iloc[idx]['domestic_delivery_failed_geolocation'])
                    if ff and haversine(d[1], d[0], ff[1], ff[0]) >= 1.0:
                        flags.append('Final Attempt')
                        df.at[idx, 'flag_fake_attempt_lm_geolocation'] = 1
                
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
                    fm_daily = fm_with_ts.groupby(['fm_courier_id', 'fm_activity_day']).agg(
                        fm_total=('lvl2_domestic_pickup/sign_in_failure_ts', 'count'),
                        fm_last_ts=('lvl2_domestic_pickup/sign_in_failure_ts', 'max')
                    ).reset_index()
                    
                    fm_daily['fm_30m_cutoff'] = fm_daily['fm_last_ts'] - pd.Timedelta(minutes=30)
                    fm_daily['fm_last_30m'] = fm_daily.apply(
                        lambda r: len(fm_with_ts[(fm_with_ts['fm_courier_id'] == r['fm_courier_id']) & 
                                                 (fm_with_ts['fm_activity_day'] == r['fm_activity_day']) & 
                                                 (fm_with_ts['lvl2_domestic_pickup/sign_in_failure_ts'] >= r['fm_30m_cutoff'])]), axis=1
                    )
                    
                    fm_daily['fm_eod_failure_rate_pct'] = (fm_daily['fm_last_30m'] / fm_daily['fm_total'] * 100).round(2)
                    fm_daily['fm_failure_tier'] = fm_daily['fm_eod_failure_rate_pct'].apply(
                        lambda x: 'a. FM Courier Failure Rate 20% and below' if x <= 20
                        else 'b. FM Courier Failure Rate 50% and below' if x <= 50
                        else 'c. Potential Fake Attempt - FM Courier Failure Rate above 50%'
                    )
                    
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
                for col in ['lvl2_domestic_1st_attempt_failed_ts', 'lvl2_domestic_reattempts_failed_ts', 'lvl2_domestic_delivery_failed_ts']:
                    if col in df.columns:
                        df[col] = pd.to_datetime(df[col], errors='coerce')
                
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
                        lm_daily = lm_all.groupby(['lm_courier_id', 'lm_activity_day']).agg(
                            lm_total=('lm_failure_ts', 'count'),
                            lm_last_ts=('lm_failure_ts', 'max')
                        ).reset_index()
                        
                        lm_daily['lm_30m_cutoff'] = lm_daily['lm_last_ts'] - pd.Timedelta(minutes=30)
                        lm_daily['lm_last_30m'] = lm_daily.apply(
                            lambda r: len(lm_all[(lm_all['lm_courier_id'] == r['lm_courier_id']) & 
                                                (lm_all['lm_activity_day'] == r['lm_activity_day']) & 
                                                (lm_all['lm_failure_ts'] >= r['lm_30m_cutoff'])]), axis=1
                        )
                        
                        lm_daily['lm_eod_failure_rate_pct'] = (lm_daily['lm_last_30m'] / lm_daily['lm_total'] * 100).round(2)
                        lm_daily['lm_failure_tier'] = lm_daily['lm_eod_failure_rate_pct'].apply(
                            lambda x: 'a. LM Courier Failure Rate 20% and below' if x <= 20
                            else 'b. LM Courier Failure Rate 50% and below' if x <= 50
                            else 'c. Potential Fake Attempt - LM Courier Failure Rate above 50%'
                        )
                        
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
        
        # === SLA BREACH DETECTION ===
        df['is_forward_soft_breach'] = 0
        df['is_forward_hard_breach'] = 0
        df['is_rts_soft_breach'] = 0
        df['is_rts_hard_breach'] = 0
        
        try:
            if 'forward_delivery_compliance' in df.columns:
                df['is_forward_soft_breach'] = ((df['forward_delivery_compliance'] == 'soft_breach').astype(int))
                df['is_forward_hard_breach'] = ((df['forward_delivery_compliance'] == 'hard_breach').astype(int))
            
            if 'rts_delivery_compliance' in df.columns:
                df['is_rts_soft_breach'] = ((df['rts_delivery_compliance'] == 'soft_breach').astype(int))
                df['is_rts_hard_breach'] = ((df['rts_delivery_compliance'] == 'hard_breach').astype(int))
        except Exception as e:
            pass
        
        return df
    
    except Exception as e:
        st.warning(f"Anomaly detection issue: {str(e)}")
        return df


def get_time_column(series, granularity):
    """Extract time bucket from timestamp series based on granularity."""
    try:
        if granularity == "Daily":
            return series.dt.date
        elif granularity == "Weekly":
            return series.dt.isocalendar().week.astype(str).str.zfill(2) + "-W" + series.dt.strftime("%B")
        elif granularity == "Monthly":
            return series.dt.strftime("%Y-%m")
    except:
        return series.dt.date if hasattr(series, 'dt') else series


def apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl, 
                  origin_region, origin_address_id, dest_region, dest_address_id):
    """Apply all filters to dataframe."""
    df_filtered = df.copy()
    
    if oc_dates and 'order_create_ts' in df_filtered.columns:
        df_filtered['order_create_ts'] = pd.to_datetime(df_filtered['order_create_ts'], errors='coerce')
        df_filtered = df_filtered[(df_filtered['order_create_ts'].dt.date >= oc_dates[0]) & 
                                 (df_filtered['order_create_ts'].dt.date <= oc_dates[1])]
    
    if rfh_dates and 'lvl1_READY_FOR_HANDOVER_ts' in df_filtered.columns:
        df_filtered['lvl1_READY_FOR_HANDOVER_ts'] = pd.to_datetime(df_filtered['lvl1_READY_FOR_HANDOVER_ts'], errors='coerce')
        df_filtered = df_filtered[(df_filtered['lvl1_READY_FOR_HANDOVER_ts'].dt.date >= rfh_dates[0]) & 
                                 (df_filtered['lvl1_READY_FOR_HANDOVER_ts'].dt.date <= rfh_dates[1])]
    
    if transit_dates and 'lvl1_IN_TRANSIT_ts' in df_filtered.columns:
        df_filtered['lvl1_IN_TRANSIT_ts'] = pd.to_datetime(df_filtered['lvl1_IN_TRANSIT_ts'], errors='coerce')
        df_filtered = df_filtered[(df_filtered['lvl1_IN_TRANSIT_ts'].dt.date >= transit_dates[0]) & 
                                 (df_filtered['lvl1_IN_TRANSIT_ts'].dt.date <= transit_dates[1])]
    
    if final_dates and 'lvl1_final_status_ts' in df_filtered.columns:
        df_filtered['lvl1_final_status_ts'] = pd.to_datetime(df_filtered['lvl1_final_status_ts'], errors='coerce')
        df_filtered = df_filtered[(df_filtered['lvl1_final_status_ts'].dt.date >= final_dates[0]) & 
                                 (df_filtered['lvl1_final_status_ts'].dt.date <= final_dates[1])]
    
    if three_pl != "All 3PLs" and 'lm_3pl_name' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['lm_3pl_name'] == three_pl]
    
    if origin_region != "All Regions" and 'origin_region' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['origin_region'] == origin_region]
    
    if origin_address_id != "All Addresses" and 'lvl2_origin_address_id' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['lvl2_origin_address_id'] == origin_address_id]
    
    if dest_region != "All Regions" and 'destination_region' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['destination_region'] == dest_region]
    
    if dest_address_id != "All Addresses" and 'lvl2_destination_address_id' in df_filtered.columns:
        df_filtered = df_filtered[df_filtered['lvl2_destination_address_id'] == dest_address_id]
    
    return df_filtered


# ============================================================================
# PHASE 2 FEATURE FUNCTIONS
# ============================================================================

def build_courier_scorecard(df, dimension_cols):
    """
    Build courier performance scorecard with proper type handling.
    """
    try:
        if df.empty:
            return None
        
        # Filter to completed orders only
        completed = df[(df['final_status'].notna()) & (df['final_status'] != '')].copy()
        
        if completed.empty:
            return None
        
        # Build metrics per dimension
        metrics = []
        for dims in completed.groupby(dimension_cols):
            group = dims[1]
            
            # Count metrics
            delivered = (group['final_status'] == 'DELIVERED').sum()
            failed = (group['final_status'].isin(['RETURNED', 'PACKAGE_DAMAGED', 'PACKAGE_LOST'])).sum()
            total = delivered + failed
            
            success_pct = (delivered / total * 100) if total > 0 else 0
            failed_pct = (failed / total * 100) if total > 0 else 0
            
            # Lead time (use numeric conversion)
            lead_times = pd.to_numeric(group['rfh_to_fa_days'], errors='coerce')
            avg_lead_time = lead_times.mean() if not lead_times.empty else 0
            
            # EOD failure rate (if column exists)
            eod_rate = pd.to_numeric(group['lm_eod_failure_rate_pct'], errors='coerce').mean()
            eod_rate = eod_rate if pd.notna(eod_rate) else 0
            
            # Handle both scalar and tuple dimension values
            if isinstance(dims[0], tuple):
                dim_val = dims[0]
            else:
                dim_val = (dims[0],)  # Convert scalar to tuple
            
            row = {**dict(zip(dimension_cols, dim_val))}
            row['Success %'] = round(success_pct, 1)
            row['Failed %'] = round(failed_pct, 1)
            row['Avg Lead Time (days)'] = round(avg_lead_time, 1)
            row['EOD Failure Rate %'] = round(eod_rate, 1)
            row['Orders'] = total
            
            metrics.append(row)
        
        return pd.DataFrame(metrics) if metrics else None
    
    except Exception as e:
        st.error(f"Courier scorecard error: {str(e)}")
        return None


def build_route_matrix(df_filtered):
    """Feature 2: Route Performance Matrix (10x10 heatmap)."""
    try:
        if df_filtered.empty or 'origin_region' not in df_filtered.columns or 'destination_region' not in df_filtered.columns:
            return None
        
        # Calculate SLA compliance by route
        route_data = df_filtered.copy()
        route_data['compliant'] = (route_data['forward_delivery_compliance'] == 'pass').astype(int)
        
        # Aggregate by route - use simple aggregations
        route_agg = route_data.groupby(['origin_region', 'destination_region'], dropna=False).agg({
            'compliant': ['sum', 'count']
        }).reset_index()
        
        # Flatten multi-level columns properly
        route_agg.columns = ['origin_region', 'destination_region', 'compliant_count', 'total']
        
        # Calculate SLA compliance %
        route_agg['sla_compliance_pct'] = (route_agg['compliant_count'] / route_agg['total'].replace(0, 1) * 100).round(1)
        
        # Create pivot for heatmap
        heatmap_data = route_agg.pivot_table(
            index='origin_region',
            columns='destination_region',
            values='sla_compliance_pct',
            aggfunc='mean'
        )
        
        # Build heatmap with Plotly
        hover_text = []
        for origin in route_agg['origin_region'].unique():
            row_hover = []
            for dest in route_agg['destination_region'].unique():
                subset = route_agg[(route_agg['origin_region'] == origin) & (route_agg['destination_region'] == dest)]
                if not subset.empty:
                    sla = subset['sla_compliance_pct'].values[0]
                    lead = subset['avg_lead_time'].values[0]
                    cpp = subset['avg_cpp'].values[0]
                    vol = int(subset['total'].values[0])
                    hover_text.append(f"Route {origin}→{dest}<br>SLA: {sla:.1f}%<br>Lead Time: {lead:.1f}d<br>CPP: ₱{cpp:.2f}<br>Volume: {vol}")
                else:
                    hover_text.append(f"No data: {origin}→{dest}")
        
        fig = go.Figure(data=go.Heatmap(
            z=heatmap_data.values,
            x=heatmap_data.columns,
            y=heatmap_data.index,
            colorscale='RdYlGn',
            zmid=90,
            text=heatmap_data.values.round(1),
            texttemplate='%{text:.1f}%',
            textfont={"size": 10},
            hovertemplate='%{customdata}<extra></extra>',
            customdata=np.array(hover_text).reshape(heatmap_data.shape)
        ))
        
        fig.update_layout(
            title="Route Performance Matrix (SLA Compliance %)",
            xaxis_title="Destination Region",
            yaxis_title="Origin Region",
            height=500,
            width=800
        )
        
        return fig
    
    except Exception as e:
        st.error(f"Route matrix error: {str(e)}")
        return None


def build_breach_prediction(df_filtered):
    """Feature 3: Breach Prediction - At-Risk Orders."""
    try:
        if df_filtered.empty:
            return None
        
        # Filter to in-transit orders only
        in_transit = df_filtered[(df_filtered['final_status'].isna()) | (df_filtered['final_status'] == '')].copy()
        
        if in_transit.empty:
            return None
        
        # Calculate remaining SLA
        current_date = pd.Timestamp.now().date()
        in_transit['lvl1_IN_TRANSIT_ts'] = pd.to_datetime(in_transit['lvl1_IN_TRANSIT_ts'], errors='coerce')
        
        # Filter out rows where conversion failed
        in_transit = in_transit[in_transit['lvl1_IN_TRANSIT_ts'].notna()]
        
        if in_transit.empty:
            return None
        
        # Assume forward SLA is 3 days (configurable)
        forward_sla_days = 3
        in_transit['sla_target_date'] = in_transit['lvl1_IN_TRANSIT_ts'] + pd.to_timedelta(forward_sla_days, unit='D')
        in_transit['days_remaining'] = (in_transit['sla_target_date'] - pd.Timestamp.now()).dt.days
        
        # Calculate risk level
        def get_risk_level(days):
            if days <= 1:
                return 'HIGH'
            elif days <= 2:
                return 'MEDIUM'
            else:
                return 'LOW'
        
        in_transit['risk_level'] = in_transit['days_remaining'].apply(get_risk_level)
        
        # Get current status (estimate completion)
        in_transit['current_status'] = in_transit['final_status'].fillna('IN_TRANSIT')
        
        # Build display dataframe
        risk_df = in_transit[[
            'tracking_number', 'current_status', 'origin_region', 'destination_region',
            'sla_target_date', 'days_remaining', 'risk_level', 'rfh_to_fa_days'
        ]].copy()
        
        risk_df.columns = [
            'Tracking #', 'Status', 'Origin', 'Destination',
            'SLA Target', 'Days Remaining', 'Risk Level', 'Avg Lead Time'
        ]
        
        # Sort by days remaining and limit to top 20
        risk_df = risk_df.sort_values('Days Remaining').head(20)
        
        return risk_df
    
    except Exception as e:
        st.error(f"Breach prediction error: {str(e)}")
        return None


def build_3pl_comparison(df_filtered):
    """Feature 4: 3PL Comparative Analysis."""
    try:
        if df_filtered.empty or 'lm_3pl_name' not in df_filtered.columns:
            return None
        
        comparison_data = df_filtered.copy()
        comparison_data['delivered'] = (comparison_data['final_status'] == 'DELIVERED').astype(int)
        comparison_data['failed'] = (comparison_data['final_status'].isin(['RETURNED', 'FAILED'])).astype(int)
        comparison_data['compliant'] = (comparison_data['forward_delivery_compliance'] == 'pass').astype(int)
        comparison_data['actual_shipping_fee'] = pd.to_numeric(comparison_data['actual_shipping_fee'], errors='coerce')
        
        # Group by 3PL
        by_3pl = comparison_data.groupby('lm_3pl_name').agg({
            'actual_shipping_fee': ['sum', 'mean', 'count'],
            'delivered': 'sum',
            'failed': 'sum',
            'compliant': 'sum',
            'rfh_to_fa_days': 'mean'
        }).reset_index()
        
        by_3pl.columns = ['_'.join(col).strip('_') if col[1] else col[0] for col in by_3pl.columns.values]
        by_3pl.rename(columns={
            'lm_3pl_name': '3PL',
            'actual_shipping_fee_sum': 'total_fees',
            'actual_shipping_fee_mean': 'avg_cpp',
            'actual_shipping_fee_count': 'volume',
            'delivered_sum': 'delivered_count',
            'failed_sum': 'failed_count',
            'compliant_sum': 'compliant_count',
            'rfh_to_fa_days_mean': 'avg_lead_time'
        }, inplace=True)
        
        # Calculate percentages
        by_3pl['sla_compliance_pct'] = (by_3pl['compliant_count'] / by_3pl['volume'].replace(0, np.nan) * 100).round(1)
        by_3pl['failed_pct'] = (by_3pl['failed_count'] / (by_3pl['delivered_count'] + by_3pl['failed_count']).replace(0, np.nan) * 100).round(1)
        
        # Build comparison table (manual for now, handling 2 3PLs)
        result = []
        
        metrics = [
            ('Avg CPP', 'avg_cpp', lambda x: f"₱{x:.2f}"),
            ('SLA Compliance %', 'sla_compliance_pct', lambda x: f"{x:.1f}%"),
            ('Failed Delivery %', 'failed_pct', lambda x: f"{x:.1f}%"),
            ('Avg Lead Time', 'avg_lead_time', lambda x: f"{x:.1f}d"),
            ('Volume', 'volume', lambda x: f"{int(x)}")
        ]
        
        for metric_name, col, fmt in metrics:
            row = {'Metric': metric_name}
            values = []
            for idx, row_data in by_3pl.iterrows():
                val = row_data[col]
                row[row_data['3PL']] = fmt(val) if pd.notna(val) else 'N/A'
                values.append(val)
            
            # Calculate delta and winner
            if len(values) == 2 and all(pd.notna(v) for v in values):
                delta = abs(values[0] - values[1])
                if 'Avg CPP' in metric_name or 'Failed' in metric_name or 'Lead Time' in metric_name:
                    winner = by_3pl.iloc[np.argmin(values)]['3PL']
                else:
                    winner = by_3pl.iloc[np.argmax(values)]['3PL']
                row['Delta'] = f"{abs(values[0] - values[1]):.2f}"
                row['Winner'] = f"{winner} ✓"
            
            result.append(row)
        
        return pd.DataFrame(result)
    
    except Exception as e:
        st.error(f"3PL comparison error: {str(e)}")
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
# GLOBAL FILTER ROW
# ============================================================================

st.markdown("### 📊 Global Filters & Dimensions")

col1, col2, col3, col4, col5, col6 = st.columns(6)

with col1:
    three_pl_options = ["All 3PLs"]
    if 'lm_3pl_name' in df.columns:
        three_pl_options += list(df['lm_3pl_name'].dropna().unique())
    three_pl = st.selectbox("3PL Partner", three_pl_options, help="Select 3PL or view all")

with col2:
    origin_region_options = ["All Regions"]
    if 'origin_region' in df.columns:
        origin_region_options += list(df['origin_region'].dropna().unique())
    origin_region = st.selectbox("Origin Region", origin_region_options, help="Select origin region or view all")

with col3:
    origin_address_options = ["All Addresses"]
    if 'lvl2_origin_address_id' in df.columns:
        if origin_region != "All Regions":
            filtered_by_origin = df[df['origin_region'] == origin_region]
            origin_address_options += list(filtered_by_origin['lvl2_origin_address_id'].dropna().unique())
        else:
            origin_address_options += list(df['lvl2_origin_address_id'].dropna().unique())
    origin_address_id = st.selectbox("Origin Address ID", origin_address_options, help="Select origin address or view all")

with col4:
    dest_region_options = ["All Regions"]
    if 'destination_region' in df.columns:
        dest_region_options += list(df['destination_region'].dropna().unique())
    dest_region = st.selectbox("Destination Region", dest_region_options, help="Select destination region or view all")

with col5:
    dest_address_options = ["All Addresses"]
    if 'lvl2_destination_address_id' in df.columns:
        if dest_region != "All Regions":
            filtered_by_dest = df[df['destination_region'] == dest_region]
            dest_address_options += list(filtered_by_dest['lvl2_destination_address_id'].dropna().unique())
        else:
            dest_address_options += list(df['lvl2_destination_address_id'].dropna().unique())
    dest_address_id = st.selectbox("Destination Address ID", dest_address_options, help="Select destination address or view all")

with col6:
    granularity = st.radio("Time Granularity", ["Daily", "Weekly", "Monthly"], horizontal=True, help="Grouping for trends")

st.divider()

# Date filters
col_d1, col_d2, col_d3, col_d4 = st.columns(4)

with col_d1:
    oc_dates = st.date_input("Order Create Date", value=[], max_value=datetime.now().date(), help="Leave blank for all dates")
    oc_dates = tuple(oc_dates) if len(oc_dates) == 2 else None

with col_d2:
    rfh_dates = st.date_input("Request Handover Date", value=[], max_value=datetime.now().date(), help="When seller marked ready")
    rfh_dates = tuple(rfh_dates) if len(rfh_dates) == 2 else None

with col_d3:
    transit_dates = st.date_input("In Transit Date", value=[], max_value=datetime.now().date(), help="When 3PL received")
    transit_dates = tuple(transit_dates) if len(transit_dates) == 2 else None

with col_d4:
    final_dates = st.date_input("Final Status Date", value=[], max_value=datetime.now().date(), help="When parcel completed")
    final_dates = tuple(final_dates) if len(final_dates) == 2 else None

st.divider()

# Apply filters
df_filtered = apply_filters(df, oc_dates, rfh_dates, transit_dates, final_dates, granularity, three_pl, 
                           origin_region, origin_address_id, dest_region, dest_address_id)

if df_filtered.empty:
    st.warning("⚠️ No data matches selected filters")
    st.stop()

# ============================================================================
# MAIN TABS LAYOUT
# ============================================================================

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 EXECUTIVE",
    "⚙️ OPERATIONS",
    "💰 COST",
    "📈 PERFORMANCE",
    "🚨 EXCEPTIONS",
    "🔮 FORECASTING"
])

# ============================================================================
# TAB 1: EXECUTIVE
# ============================================================================

with tab1:
    st.header("Executive Dashboard")
    
    # Row 1: KPI Cards
    try:
        sla_compliance = (df_filtered['forward_delivery_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        failed_delivery = (df_filtered['final_status'].isin(['RETURNED'])).sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        cpp = pd.to_numeric(df_filtered['actual_shipping_fee'], errors='coerce').mean()
        volume = len(df_filtered)
        
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric("1a. SLA Compliance %", f"{sla_compliance:.1f}%", delta="Target: >95%")
        
        with col2:
            st.metric("2a. Failed Delivery %", f"{failed_delivery:.1f}%", delta="Target: <5%")
        
        with col3:
            st.metric("Cost Per Parcel", f"₱{cpp:.2f}", delta="Target: ₱81.04")
        
        with col4:
            st.metric("Volume", f"{volume}", delta=f"In-transit: {len(df_filtered[(df_filtered['final_status'].isna()) | (df_filtered['final_status'] == '')])}")
    except Exception as e:
        st.error(f"KPI error: {str(e)}")
    
    st.divider()
    
    # Row 2: 3PL Volume Pie + Top 5 Issues
    try:
        col_pie, col_issues = st.columns(2)
        
        with col_pie:
            if three_pl == "All 3PLs":
                three_pl_volumes = df_filtered['lm_3pl_name'].value_counts()
                if len(three_pl_volumes) > 0:
                    fig_pie = go.Figure(data=[go.Pie(
                        labels=three_pl_volumes.index,
                        values=three_pl_volumes.values,
                        hovertemplate='<b>%{label}</b><br>Volume: %{value}<br>%{percent}<extra></extra>'
                    )])
                    fig_pie.update_layout(title="3PL Volume Control", height=350)
                    st.plotly_chart(fig_pie, use_container_width=True)
        
        with col_issues:
            st.markdown("**Top 5 Issues by Count**")
            issues = []
            
            if (df_filtered['flag_fake_attempt_fm_geolocation'] == 1).any():
                issues.append(("FM Geolocation Violations", (df_filtered['flag_fake_attempt_fm_geolocation'] == 1).sum()))
            if (df_filtered['flag_fake_attempt_lm_geolocation'] == 1).any():
                issues.append(("LM Geolocation Violations", (df_filtered['flag_fake_attempt_lm_geolocation'] == 1).sum()))
            if (df_filtered['is_package_lost'] == 1).any():
                issues.append(("Lost Packages", (df_filtered['is_package_lost'] == 1).sum()))
            if (df_filtered['is_package_damaged'] == 1).any():
                issues.append(("Damaged Packages", (df_filtered['is_package_damaged'] == 1).sum()))
            if (df_filtered['is_forward_hard_breach'] == 1).any():
                issues.append(("Forward Hard Breaches", (df_filtered['is_forward_hard_breach'] == 1).sum()))
            
            issues_df = pd.DataFrame(issues, columns=['Issue', 'Count']).sort_values('Count', ascending=False).head(5)
            st.dataframe(issues_df, use_container_width=True, height=200)
    
    except Exception as e:
        st.error(f"Pie/Issues error: {str(e)}")
    
    st.divider()
    
    # Row 3: 4 Trend Lines
    try:
        trend_col1, trend_col2, trend_col3, trend_col4 = st.columns(4)
        
        with trend_col1:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend_sla = df_trend.groupby('time_bucket').apply(
                    lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend_sla.columns = ['time_bucket', 'sla_pct']
                
                if not trend_sla.empty:
                    fig_sla = go.Figure()
                    fig_sla.add_trace(go.Scatter(x=trend_sla['time_bucket'].astype(str), y=trend_sla['sla_pct'],
                        mode='lines+markers', line=dict(color='#2ca02c', width=2), marker=dict(size=5)))
                    fig_sla.update_layout(title="SLA Compliance % Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                    st.plotly_chart(fig_sla, use_container_width=True)
        
        with trend_col2:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend_failed = df_trend.groupby('time_bucket').apply(
                    lambda x: (x['final_status'].isin(['RETURNED'])).sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend_failed.columns = ['time_bucket', 'failed_pct']
                
                if not trend_failed.empty:
                    fig_failed = go.Figure()
                    fig_failed.add_trace(go.Scatter(x=trend_failed['time_bucket'].astype(str), y=trend_failed['failed_pct'],
                        mode='lines+markers', line=dict(color='#d62728', width=2), marker=dict(size=5)))
                    fig_failed.update_layout(title="Failed Delivery % Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                    st.plotly_chart(fig_failed, use_container_width=True)
        
        with trend_col3:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend_cpp = df_trend.groupby('time_bucket')['actual_shipping_fee'].apply(
                    lambda x: pd.to_numeric(x, errors='coerce').mean()
                ).reset_index()
                trend_cpp.columns = ['time_bucket', 'cpp']
                
                if not trend_cpp.empty:
                    fig_cpp = go.Figure()
                    fig_cpp.add_trace(go.Scatter(x=trend_cpp['time_bucket'].astype(str), y=trend_cpp['cpp'],
                        mode='lines+markers', line=dict(color='#1f77b4', width=2), marker=dict(size=5)))
                    fig_cpp.add_hline(y=81.04, line_dash="dash", line_color="red")
                    fig_cpp.update_layout(title="CPP Trend", height=300, xaxis_title=granularity, yaxis_title="₱")
                    st.plotly_chart(fig_cpp, use_container_width=True)
        
        with trend_col4:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend_vol = df_trend.groupby('time_bucket').size().reset_index(name='volume')
                
                if not trend_vol.empty:
                    fig_vol = go.Figure()
                    fig_vol.add_trace(go.Scatter(x=trend_vol['time_bucket'].astype(str), y=trend_vol['volume'],
                        mode='lines+markers', line=dict(color='#ff7f0e', width=2), marker=dict(size=5)))
                    fig_vol.update_layout(title="Volume Trend", height=300, xaxis_title=granularity, yaxis_title="Orders")
                    st.plotly_chart(fig_vol, use_container_width=True)
    
    except Exception as e:
        st.error(f"Trend error: {str(e)}")


# ============================================================================
# TAB 2: OPERATIONS
# ============================================================================

with tab2:
    st.header("Operations Control Center")
    
    # SECTION A: Global Filters already shown above
    st.markdown("*Filters applied globally across all tabs*")
    st.divider()
    
    # SECTION B: Operations Scorecard
    st.markdown("### SECTION B: Operations Scorecard - Pivot Table")
    
    try:
        available_dimensions = []
        if 'origin_region' in df_filtered.columns:
            available_dimensions.append('origin_region')
        if 'destination_region' in df_filtered.columns:
            available_dimensions.append('destination_region')
        if 'fm_3pl_name' in df_filtered.columns:
            available_dimensions.append('fm_3pl_name')
        if 'lm_3pl_name' in df_filtered.columns:
            available_dimensions.append('lm_3pl_name')
        
        if available_dimensions:
            selected_dimensions = st.multiselect(
                "Select Row Dimensions for Operations Scorecard",
                available_dimensions,
                default=available_dimensions[:2] if len(available_dimensions) >= 2 else available_dimensions,
                key="ops_dimensions"
            )
            
            if selected_dimensions:
                pivot_data = df_filtered.copy()
                pivot_data['pickup_compliance'] = (pivot_data.get('pickup_sla_compliance', '') == 'pass').astype(int)
                pivot_data['forward_compliance'] = (pivot_data.get('forward_delivery_compliance', '') == 'pass').astype(int)
                pivot_data['failed_delivery'] = pivot_data['final_status'].isin(['FAILED', 'RTS']).astype(int)
                
                agg_dict = {
                    'pickup_compliance': ['sum', 'count'],
                    'forward_compliance': ['sum', 'count'],
                    'oc_to_rfh_days': 'mean',
                    'rfh_to_fa_days': 'mean',
                    'failed_delivery': ['sum', 'count']
                }
                
                scorecard = pivot_data.groupby(selected_dimensions, dropna=False).agg(agg_dict).reset_index()
                scorecard.columns = ['_'.join(col).strip('_') if col[1] else col[0] for col in scorecard.columns.values]
                
                rename_map = {
                    'pickup_compliance_sum': 'Pickup_Pass',
                    'pickup_compliance_count': 'Pickup_Total',
                    'forward_compliance_sum': 'Forward_Pass',
                    'forward_compliance_count': 'Forward_Total',
                    'oc_to_rfh_days_mean': 'OC_to_RFH',
                    'rfh_to_fa_days_mean': 'RFH_to_FA',
                    'failed_delivery_sum': 'Failed_Count',
                    'failed_delivery_count': 'Delivery_Total'
                }
                scorecard = scorecard.rename(columns=rename_map)
                
                scorecard['Pickup_%'] = (scorecard['Pickup_Pass'] / scorecard['Pickup_Total'].replace(0, np.nan) * 100).round(2)
                scorecard['Forward_%'] = (scorecard['Forward_Pass'] / scorecard['Forward_Total'].replace(0, np.nan) * 100).round(2)
                scorecard['Failed_%'] = (scorecard['Failed_Count'] / scorecard['Delivery_Total'].replace(0, np.nan) * 100).round(2)
                
                display_cols = selected_dimensions + ['Pickup_%', 'Forward_%', 'OC_to_RFH', 'RFH_to_FA', 'Failed_%']
                display_cols = [col for col in display_cols if col in scorecard.columns]
                
                st.dataframe(scorecard[display_cols].style.format({col: '{:.2f}' for col in scorecard[display_cols].columns if '%' in col or 'days' in col.lower()}), use_container_width=True, height=350)
    
    except Exception as e:
        st.warning(f"Operations scorecard error: {str(e)}")
    
    st.divider()
    
    # SECTION C: Removed - Merged into Section B
    st.divider()
    st.caption("💡 Tip: Use 'fm_3pl_name' or 'lm_3pl_name' in Section B filters above to analyze Courier Performance by 3PL")
    
    # SECTION D: Route Performance Matrix (PHASE 2B - Coming Soon)
    st.markdown("### SECTION D: Route Performance Matrix (Phase 2B)")
    st.info("🔄 Coming in Phase 2B...")
    
    st.divider()
    
    st.divider()
    
    # SECTION E: Breach Prediction (PHASE 2C - LIVE)
    st.markdown("### SECTION E: Breach Prediction - At-Risk Orders (Phase 2C)")
    
    sla_ref = {
        ('GMA', 'GMA'): {'forward_delivery_sla': 2},
        ('GMA', 'Luzon 1'): {'forward_delivery_sla': 3},
        ('GMA', 'Luzon 2'): {'forward_delivery_sla': 5},
        ('GMA', 'Luzon 3'): {'forward_delivery_sla': 10},
        ('GMA', 'Luzon 4'): {'forward_delivery_sla': 18},
        ('GMA', 'Visayas 1'): {'forward_delivery_sla': 5},
        ('GMA', 'Visayas 2'): {'forward_delivery_sla': 8},
        ('GMA', 'Visayas 3'): {'forward_delivery_sla': 10},
        ('GMA', 'Mindanao 1'): {'forward_delivery_sla': 8},
        ('GMA', 'Mindanao 2'): {'forward_delivery_sla': 12},
    }
    
    mp_baselines = {
        ('GMA', 'GMA'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 4, 'mp4_p90_hours': 12, 'mp5_p90_hours': 2, 'mp6_p90_hours': 2, 'mp7_p90_hours': 4},
        ('GMA', 'Luzon 1'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 6, 'mp4_p90_hours': 12, 'mp5_p90_hours': 4, 'mp6_p90_hours': 4, 'mp7_p90_hours': 4},
        ('GMA', 'Luzon 2'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 10, 'mp4_p90_hours': 12, 'mp5_p90_hours': 6, 'mp6_p90_hours': 4, 'mp7_p90_hours': 6},
        ('GMA', 'Luzon 3'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 12, 'mp4_p90_hours': 12, 'mp5_p90_hours': 12, 'mp6_p90_hours': 4, 'mp7_p90_hours': 8},
        ('GMA', 'Luzon 4'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 48, 'mp4_p90_hours': 12, 'mp5_p90_hours': 12, 'mp6_p90_hours': 4, 'mp7_p90_hours': 8},
        ('GMA', 'Visayas 1'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 18, 'mp4_p90_hours': 12, 'mp5_p90_hours': 12, 'mp6_p90_hours': 4, 'mp7_p90_hours': 6},
        ('GMA', 'Visayas 2'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 18, 'mp4_p90_hours': 12, 'mp5_p90_hours': 12, 'mp6_p90_hours': 4, 'mp7_p90_hours': 6},
        ('GMA', 'Visayas 3'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 18, 'mp4_p90_hours': 12, 'mp5_p90_hours': 12, 'mp6_p90_hours': 4, 'mp7_p90_hours': 6},
        ('GMA', 'Mindanao 1'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 30, 'mp4_p90_hours': 12, 'mp5_p90_hours': 16, 'mp6_p90_hours': 4, 'mp7_p90_hours': 8},
        ('GMA', 'Mindanao 2'): {'mp1_p90_hours': 6, 'mp2_p90_hours': 4, 'mp3_p90_hours': 30, 'mp4_p90_hours': 12, 'mp5_p90_hours': 16, 'mp6_p90_hours': 4, 'mp7_p90_hours': 8},
    }
    
    breach_results = []
    for idx, row in df_filtered.iterrows():
        try:
            route = (row.get('origin_region', 'GMA'), row.get('destination_region', 'GMA'))
            if route in sla_ref and route in mp_baselines:
                t3_start = pd.to_datetime(row.get('lvl1_IN_TRANSIT_ts'), errors='coerce')
                t3_end = pd.to_datetime(row.get('lvl2_first_attempt_ts'), errors='coerce')
                
                if pd.notna(t3_start):
                    sla_days = sla_ref[route]['forward_delivery_sla']
                    sla_target = t3_start + timedelta(days=sla_days)
                    
                    if pd.notna(t3_end):
                        elapsed = (t3_end - t3_start).total_seconds() / 3600 / 24
                        t3_remaining = 0
                        status = 'ON_TIME' if t3_end <= sla_target else 'BREACH'
                    else:
                        elapsed = (datetime.now() - t3_start).total_seconds() / 3600 / 24
                        t3_remaining = (sla_target - datetime.now()).total_seconds() / 3600 / 24
                        status = 'ON_TRACK' if t3_remaining > 0 else 'BREACH'
                    
                    buffer_days = sla_days - elapsed if pd.notna(t3_end) else t3_remaining
                    
                    if buffer_days > 1:
                        risk = 'LOW'
                    elif buffer_days > 0:
                        risk = 'MEDIUM'
                    elif buffer_days > -1:
                        risk = 'HIGH'
                    else:
                        risk = 'CRITICAL'
                    
                    breach_results.append({
                        'tracking': row.get('tracking_number', f'TRK{idx}'),
                        'route': f"{route[0]}→{route[1]}",
                        't3_status': status,
                        't3_remaining_days': t3_remaining,
                        'buffer_days': buffer_days,
                        'risk_tier': risk,
                        'current_phase': 'In Progress' if pd.isna(t3_end) else 'Delivered'
                    })
        except:
            pass
    
    if breach_results:
        results_df = pd.DataFrame(breach_results)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("🟢 LOW", len(results_df[results_df['risk_tier']=='LOW']))
        with col2:
            st.metric("🟡 MEDIUM", len(results_df[results_df['risk_tier']=='MEDIUM']))
        with col3:
            st.metric("🔴 HIGH", len(results_df[results_df['risk_tier']=='HIGH']))
        with col4:
            st.metric("🔴🔴 CRITICAL", len(results_df[results_df['risk_tier']=='CRITICAL']))
        
        st.dataframe(results_df[['tracking', 'route', 't3_status', 'buffer_days', 'risk_tier']].sort_values('risk_tier', key=lambda x: x.map({'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3})), use_container_width=True, height=300)
    else:
        st.info("No packages in-transit or at-risk.")


# ============================================================================
# TAB 3: COST
# ============================================================================

with tab3:
    st.header("Cost Control & Analysis")
    
    # SECTION A: Cost KPIs
    st.markdown("### SECTION A: Cost KPIs")
    
    try:
        cpp = pd.to_numeric(df_filtered['actual_shipping_fee'], errors='coerce').mean()
        
        # Cost variance (estimated vs actual)
        cost_variance = 0
        if 'estimated_shipping_fee' in df_filtered.columns:
            estimated = pd.to_numeric(df_filtered['estimated_shipping_fee'], errors='coerce')
            actual = pd.to_numeric(df_filtered['actual_shipping_fee'], errors='coerce')
            cost_variance = ((actual.sum() - estimated.sum()) / estimated.sum() * 100) if estimated.sum() > 0 else 0
        
        # Cost leakage (placeholder)
        cost_leakage_count = 0
        
        col_cost1, col_cost2, col_cost3 = st.columns(3)
        
        with col_cost1:
            st.metric("Total CPP (₱/parcel)", f"₱{cpp:.2f}", delta="Target: ₱81.04")
        
        with col_cost2:
            st.metric("Cost Variance %", f"{cost_variance:.1f}%", delta="Estimated vs Actual")
        
        with col_cost3:
            st.metric("Cost Leakage Count", cost_leakage_count, delta="Overweight/Overvalued")
    
    except Exception as e:
        st.error(f"Cost KPI error: {str(e)}")
    
    st.divider()
    
    # SECTION B: CPP by Route
    st.markdown("### SECTION B: CPP by Route")
    
    try:
        if 'origin_region' in df_filtered.columns and 'destination_region' in df_filtered.columns:
            route_cpp = df_filtered.copy()
            route_cpp['route'] = route_cpp['origin_region'].astype(str) + ' → ' + route_cpp['destination_region'].astype(str)
            route_cpp['actual_shipping_fee'] = pd.to_numeric(route_cpp['actual_shipping_fee'], errors='coerce')
            
            route_summary = route_cpp.groupby('route').agg({
                'actual_shipping_fee': ['mean', 'count']
            }).reset_index()
            route_summary.columns = ['route', 'avg_cpp', 'volume']
            route_summary = route_summary.sort_values('avg_cpp', ascending=False).head(10)
            
            fig_route = go.Figure(data=[
                go.Bar(x=route_summary['route'], y=route_summary['avg_cpp'], marker=dict(color=route_summary['avg_cpp'], colorscale='RdYlGn_r'))
            ])
            fig_route.update_layout(title="Top 10 Routes by CPP", xaxis_title="Route", yaxis_title="₱", height=400)
            st.plotly_chart(fig_route, use_container_width=True)
    
    except Exception as e:
        st.warning(f"Route CPP error: {str(e)}")
    
    st.divider()
    
    # SECTION C: 3PL Comparative Analysis (PHASE 2)
    st.markdown("### SECTION C: 3PL Comparative Analysis (Phase 2)")
    
    try:
        comparison = build_3pl_comparison(df_filtered)
        if comparison is not None and not comparison.empty:
            st.dataframe(comparison, use_container_width=True, height=300)
        else:
            st.info("3PL comparison unavailable - insufficient data for 2+ 3PLs")
    
    except Exception as e:
        st.warning(f"3PL comparison error: {str(e)}")
    
    st.divider()
    
    # SECTION D: Cost Trends
    st.markdown("### SECTION D: Cost Trends")
    
    try:
        df_trend = df_filtered.copy()
        if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
            df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
            daily_cpp = df_trend.groupby('time_bucket')['actual_shipping_fee'].apply(
                lambda x: pd.to_numeric(x, errors='coerce').mean()
            ).reset_index()
            
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=daily_cpp['time_bucket'].astype(str), y=daily_cpp['actual_shipping_fee'],
                mode='lines+markers', name='CPP', line=dict(color='#1f77b4', width=2)))
            fig.add_hline(y=81.04, line_dash="dash", line_color="red", annotation_text="Target ₱81.04")
            fig.update_layout(title="CPP Trend Over Time", height=400, xaxis_title=granularity, yaxis_title="₱")
            st.plotly_chart(fig, use_container_width=True)
    
    except Exception as e:
        st.warning(f"Cost trend error: {str(e)}")


# ============================================================================
# TAB 4: PERFORMANCE
# ============================================================================

with tab4:
    st.header("Performance Metrics & Compliance")
    
    # Pickup + Forward Compliance
    st.markdown("### Pickup & Forward Compliance")
    
    try:
        pickup_comp = (df_filtered.get('pickup_sla_compliance', pd.Series()) == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        forward_comp = (df_filtered['forward_delivery_compliance'] == 'pass').sum() / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        
        col_perf1, col_perf2 = st.columns(2)
        
        with col_perf1:
            st.metric("Pickup Compliance %", f"{pickup_comp:.1f}%", delta="Target: >98%")
        
        with col_perf2:
            st.metric("Forward Compliance %", f"{forward_comp:.1f}%", delta="Target: >95%")
        
        # Trend lines
        col_trend1, col_trend2 = st.columns(2)
        
        with col_trend1:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend = df_trend.groupby('time_bucket').apply(
                    lambda x: (x.get('pickup_sla_compliance', '') == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend.columns = ['time_bucket', 'compliance']
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=trend['time_bucket'].astype(str), y=trend['compliance'],
                    mode='lines+markers', line=dict(color='#2ca02c', width=2)))
                fig.update_layout(title="Pickup Compliance Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                st.plotly_chart(fig, use_container_width=True)
        
        with col_trend2:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend = df_trend.groupby('time_bucket').apply(
                    lambda x: (x['forward_delivery_compliance'] == 'pass').sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend.columns = ['time_bucket', 'compliance']
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=trend['time_bucket'].astype(str), y=trend['compliance'],
                    mode='lines+markers', line=dict(color='#1f77b4', width=2)))
                fig.update_layout(title="Forward Compliance Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                st.plotly_chart(fig, use_container_width=True)
    
    except Exception as e:
        st.warning(f"Compliance error: {str(e)}")
    
    st.divider()
    
    # Lost & Damaged
    st.markdown("### Lost & Damaged Metrics")
    
    try:
        lost_pct = (df_filtered['is_package_lost'].sum()) / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        damaged_pct = (df_filtered['is_package_damaged'].sum()) / len(df_filtered) * 100 if len(df_filtered) > 0 else 0
        
        col_loss1, col_loss2 = st.columns(2)
        
        with col_loss1:
            st.metric("Lost %", f"{lost_pct:.1f}%", delta="vs target <0.1%")
        
        with col_loss2:
            st.metric("Damaged %", f"{damaged_pct:.1f}%", delta="vs target <0.1%")
        
        # Trends
        col_trend_loss1, col_trend_loss2 = st.columns(2)
        
        with col_trend_loss1:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend = df_trend.groupby('time_bucket').apply(
                    lambda x: (x['final_status'] == 'LOST').sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend.columns = ['time_bucket', 'lost_pct']
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=trend['time_bucket'].astype(str), y=trend['lost_pct'],
                    mode='lines+markers', line=dict(color='#ff7f0e', width=2)))
                fig.update_layout(title="Lost % Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                st.plotly_chart(fig, use_container_width=True)
        
        with col_trend_loss2:
            df_trend = df_filtered.copy()
            if 'lvl1_final_status_ts' in df_trend.columns and not df_trend.empty:
                df_trend['time_bucket'] = get_time_column(df_trend['lvl1_final_status_ts'], granularity)
                trend = df_trend.groupby('time_bucket').apply(
                    lambda x: (x['final_status'] == 'DAMAGED').sum() / len(x) * 100 if len(x) > 0 else 0
                ).reset_index()
                trend.columns = ['time_bucket', 'dmg_pct']
                
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=trend['time_bucket'].astype(str), y=trend['dmg_pct'],
                    mode='lines+markers', line=dict(color='#d62728', width=2)))
                fig.update_layout(title="Damaged % Trend", height=300, xaxis_title=granularity, yaxis_title="%")
                st.plotly_chart(fig, use_container_width=True)
    
    except Exception as e:
        st.warning(f"Lost & Damaged error: {str(e)}")
    
    st.divider()
    
    # SLA Breaches
    st.markdown("### SLA Breaches - Detailed View")
    
    try:
        sla_subtab1, sla_subtab2, sla_subtab3, sla_subtab4 = st.tabs(["Forward Soft", "Forward Hard", "RTS Soft", "RTS Hard"])
        
        with sla_subtab1:
            fwd_soft = df_filtered[df_filtered['is_forward_soft_breach'].astype(str) == '1']
            st.metric("Parcels", len(fwd_soft))
            if len(fwd_soft) > 0:
                cols = [c for c in ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region'] if c in fwd_soft.columns]
                st.dataframe(fwd_soft[cols], use_container_width=True, height=200)
            else:
                st.info("✅ No forward soft breaches")
        
        with sla_subtab2:
            fwd_hard = df_filtered[df_filtered['is_forward_hard_breach'].astype(str) == '1']
            st.metric("Parcels", len(fwd_hard))
            if len(fwd_hard) > 0:
                cols = [c for c in ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region'] if c in fwd_hard.columns]
                st.dataframe(fwd_hard[cols], use_container_width=True, height=200)
            else:
                st.info("✅ No forward hard breaches")
        
        with sla_subtab3:
            rts_soft = df_filtered[df_filtered['is_rts_soft_breach'].astype(str) == '1']
            st.metric("Parcels", len(rts_soft))
            if len(rts_soft) > 0:
                cols = [c for c in ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region'] if c in rts_soft.columns]
                st.dataframe(rts_soft[cols], use_container_width=True, height=200)
            else:
                st.info("✅ No RTS soft breaches")
        
        with sla_subtab4:
            rts_hard = df_filtered[df_filtered['is_rts_hard_breach'].astype(str) == '1']
            st.metric("Parcels", len(rts_hard))
            if len(rts_hard) > 0:
                cols = [c for c in ['lm_3pl_name', 'tracking_number', 'origin_region', 'destination_region'] if c in rts_hard.columns]
                st.dataframe(rts_hard[cols], use_container_width=True, height=200)
            else:
                st.info("✅ No RTS hard breaches")
    
    except Exception as e:
        st.warning(f"SLA breaches error: {str(e)}")


# ============================================================================
# TAB 5: EXCEPTIONS
# ============================================================================

with tab5:
    st.header("Anomaly Detection & Exception Queue")
    
    st.markdown("### Exception Filters")
    
    col_filter1, col_filter2, col_filter3 = st.columns(3)
    
    with col_filter1:
        exception_type = st.multiselect(
            "Exception Type",
            ["All", "Fake Attempts", "SLA Breaches", "Lost/Damaged", "Cost Leakage"],
            default=["All"],
            key="exc_type"
        )
    
    with col_filter2:
        priority = st.multiselect(
            "Priority",
            ["All", "High", "Medium", "Low"],
            default=["All"],
            key="exc_priority"
        )
    
    with col_filter3:
        status = st.multiselect(
            "Status",
            ["All", "Open", "Investigating", "Resolved"],
            default=["Open"],
            key="exc_status"
        )
    
    st.divider()
    
    st.markdown("### Prioritized Exception Queue")
    
    try:
        # Build exception queue
        exceptions = []
        
        # Fake attempts
        fm_geo = df_filtered[df_filtered['flag_fake_attempt_fm_geolocation'] == 1]
        for idx, row in fm_geo.iterrows():
            exceptions.append({
                'tracking_number': row.get('tracking_number', 'N/A'),
                'issue_type': 'FM Geolocation Violation',
                'priority': 'High',
                'impact': 500,  # Placeholder cost impact
                'status': 'Open'
            })
        
        lm_geo = df_filtered[df_filtered['flag_fake_attempt_lm_geolocation'] == 1]
        for idx, row in lm_geo.iterrows():
            exceptions.append({
                'tracking_number': row.get('tracking_number', 'N/A'),
                'issue_type': 'LM Geolocation Violation',
                'priority': 'High',
                'impact': 500,
                'status': 'Open'
            })
        
        # Lost packages
        lost = df_filtered[df_filtered['is_package_lost'] == 1]
        for idx, row in lost.iterrows():
            exceptions.append({
                'tracking_number': row.get('tracking_number', 'N/A'),
                'issue_type': 'Package Lost',
                'priority': 'High',
                'impact': float(row.get('actual_shipping_fee', 100)),
                'status': 'Open'
            })
        
        # Damaged packages
        damaged = df_filtered[df_filtered['is_package_damaged'] == 1]
        for idx, row in damaged.iterrows():
            exceptions.append({
                'tracking_number': row.get('tracking_number', 'N/A'),
                'issue_type': 'Package Damaged',
                'priority': 'Medium',
                'impact': float(row.get('actual_shipping_fee', 100)),
                'status': 'Open'
            })
        
        # SLA breaches
        fwd_hard = df_filtered[df_filtered['is_forward_hard_breach'] == 1]
        for idx, row in fwd_hard.iterrows():
            exceptions.append({
                'tracking_number': row.get('tracking_number', 'N/A'),
                'issue_type': 'Forward Hard Breach',
                'priority': 'High',
                'impact': 1000,
                'status': 'Open'
            })
        
        if exceptions:
            exc_df = pd.DataFrame(exceptions)
            exc_df['rank'] = range(1, len(exc_df) + 1)
            
            # Filter
            if "All" not in exception_type:
                exc_df = exc_df[exc_df['issue_type'].isin([t for t in exception_type if t != "All"])]
            
            if "All" not in priority:
                exc_df = exc_df[exc_df['priority'].isin([p for p in priority if p != "All"])]
            
            if "All" not in status:
                exc_df = exc_df[exc_df['status'].isin([s for s in status if s != "All"])]
            
            # Sort by impact
            exc_df = exc_df.sort_values('impact', ascending=False).head(50)
            
            # Color code priority
            def color_priority(val):
                if val == 'High':
                    return 'background-color: #FFB6C6'
                elif val == 'Medium':
                    return 'background-color: #FFFFE0'
                else:
                    return 'background-color: #E0FFE0'
            
            display_cols = ['rank', 'tracking_number', 'issue_type', 'priority', 'impact', 'status']
            st.dataframe(
                exc_df[display_cols].style.applymap(color_priority, subset=['priority']),
                use_container_width=True,
                height=500
            )
            
            st.caption(f"Showing {len(exc_df)} exceptions (sorted by impact). Bulk actions available via sidebar.")
        else:
            st.info("✅ No exceptions detected!")
    
    except Exception as e:
        st.warning(f"Exception queue error: {str(e)}")
    
    st.divider()
    
    # Fake Attempts Tables
    st.markdown("### Fake Attempt Analysis")
    
    try:
        fake_tab1, fake_tab2 = st.tabs(["FM Geolocation", "LM Geolocation"])
        
        with fake_tab1:
            fm_geo_df = df_filtered[df_filtered['flag_fake_attempt_fm_geolocation'] == 1]
            st.metric("FM Geolocation Violations", len(fm_geo_df))
            if len(fm_geo_df) > 0:
                cols = [c for c in ['fm_3pl_name', 'tracking_number', 'origin_region', 'fm_courier_id'] if c in fm_geo_df.columns]
                st.dataframe(fm_geo_df[cols], use_container_width=True, height=300)
            else:
                st.info("✅ No FM geolocation violations")
        
        with fake_tab2:
            lm_geo_df = df_filtered[df_filtered['flag_fake_attempt_lm_geolocation'] == 1]
            st.metric("LM Geolocation Violations", len(lm_geo_df))
            if len(lm_geo_df) > 0:
                cols = [c for c in ['lm_3pl_name', 'tracking_number', 'destination_region', 'lm_courier_id'] if c in lm_geo_df.columns]
                st.dataframe(lm_geo_df[cols], use_container_width=True, height=300)
            else:
                st.info("✅ No LM geolocation violations")
    
    except Exception as e:
        st.warning(f"Fake attempts error: {str(e)}")


# ============================================================================
# TAB 6: BREACH PREDICTION (PHASE 2C)
# ============================================================================

with tab6:
    st.header("🔮 Forecasting & Predictive Analytics")
    st.markdown("**Phase 2C: Real-Time SLA Breach Prediction** is now live in OPERATIONS tab (Section E).")
    st.info("🔄 Phase 3 features coming soon...")


st.divider()
st.markdown("---")
st.caption("🚚 MallPlus Logistics Dashboard v3.1 | Phase 2C LIVE | Last sync: " + datetime.now().strftime("%Y-%m-%d %H:%M:%S GMT+8"))
