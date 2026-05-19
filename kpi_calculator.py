"""
KPI Calculator for Route Performance Matrix (Phase 2B)

Calculates all 13 KPIs required for the enhanced Operations Scorecard:
1. Cost per Parcel (CPP)
2. Pickup Compliance (%)
3. OC to RFH Lead Time (days)
4. OC to FA Lead Time (days)
5. RFH to FA Lead Time (days)
6. RFH to FA P90 Lead Time (days)
7. Forward Delivery SLA Compliance (%)
8. Forward Journey Closure SLA Breach (%)
9. RTS Journey Closure SLA Breach (%)
10. E2E SLA Breach (%)
11. Failed Delivery/FD (%)
12. Lost (%)
13. Damaged (%)

Color Coding:
- GREEN: KPI hits or exceeds target
- YELLOW: KPI between threshold and target (TBD)
- RED: KPI below threshold (misses target)
"""

import pandas as pd
import numpy as np
from datetime import datetime


def calculate_cpp(df):
    """
    Cost Per Parcel (CPP)
    
    Formula: (Total Costs) / (Total Parcels)
    Costs include: Shipping fee + Valuation fee + Handling (assume minimal)
    
    Returns: float (PHP per parcel)
    """
    if len(df) == 0:
        return np.nan
    
    # Sum shipping + valuation fees
    total_cost = (
        df.get('estimated_shipping_fee', df.get('actual_shipping_fee', 0)).sum() +
        df.get('valuation_fee', 0).sum()
    )
    
    cpp = total_cost / len(df)
    return round(cpp, 2)


def calculate_pickup_compliance(df):
    """
    Pickup Compliance (%)
    
    Formula: (Pickups meeting SLA) / (Total pickups) * 100
    
    Field: pickup_sla_compliance == 'pass' (or YES/True)
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    pickup_pass = df[df.get('pickup_sla_compliance', '') == 'pass'].shape[0]
    pickup_pass += df[df.get('pickup_sla_compliance', '') == 'YES'].shape[0]
    pickup_pass += df[df.get('pickup_sla_compliance', '') == True].shape[0]
    
    compliance = (pickup_pass / len(df)) * 100
    return round(compliance, 2)


def calculate_oc_to_rfh_lead_time(df):
    """
    OC to RFH Lead Time (days)
    
    From: order_create_ts
    To: lvl1_REQUEST_FOR_HANDOVER_ts
    
    Returns: float (median days, or mean)
    """
    if len(df) == 0:
        return np.nan
    
    df_copy = df.copy()
    
    # Parse timestamps if string
    if df_copy['order_create_ts'].dtype == 'object':
        df_copy['order_create_ts'] = pd.to_datetime(df_copy['order_create_ts'], errors='coerce')
    if df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'].dtype == 'object':
        df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'] = pd.to_datetime(df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'], errors='coerce')
    
    # Calculate time difference
    df_copy['oc_to_rfh_diff'] = (df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'] - df_copy['order_create_ts']).dt.total_seconds() / 86400
    
    # Remove nulls and negatives
    valid = df_copy[df_copy['oc_to_rfh_diff'].notna() & (df_copy['oc_to_rfh_diff'] >= 0)]['oc_to_rfh_diff']
    
    if len(valid) == 0:
        return np.nan
    
    return round(valid.median(), 2)


def calculate_oc_to_fa_lead_time(df):
    """
    OC to FA Lead Time (days)
    
    From: order_create_ts
    To: lvl2_first_attempt_ts
    
    Returns: float (median days)
    """
    if len(df) == 0:
        return np.nan
    
    df_copy = df.copy()
    
    # Parse timestamps if string
    if df_copy['order_create_ts'].dtype == 'object':
        df_copy['order_create_ts'] = pd.to_datetime(df_copy['order_create_ts'], errors='coerce')
    if df_copy['lvl2_first_attempt_ts'].dtype == 'object':
        df_copy['lvl2_first_attempt_ts'] = pd.to_datetime(df_copy['lvl2_first_attempt_ts'], errors='coerce')
    
    # Calculate time difference
    df_copy['oc_to_fa_diff'] = (df_copy['lvl2_first_attempt_ts'] - df_copy['order_create_ts']).dt.total_seconds() / 86400
    
    # Remove nulls and negatives
    valid = df_copy[df_copy['oc_to_fa_diff'].notna() & (df_copy['oc_to_fa_diff'] >= 0)]['oc_to_fa_diff']
    
    if len(valid) == 0:
        return np.nan
    
    return round(valid.median(), 2)


def calculate_rfh_to_fa_lead_time(df):
    """
    RFH to FA Lead Time (days)
    
    From: lvl1_REQUEST_FOR_HANDOVER_ts
    To: lvl2_first_attempt_ts
    
    Returns: float (median days)
    """
    if len(df) == 0:
        return np.nan
    
    df_copy = df.copy()
    
    # Parse timestamps if string
    if df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'].dtype == 'object':
        df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'] = pd.to_datetime(df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'], errors='coerce')
    if df_copy['lvl2_first_attempt_ts'].dtype == 'object':
        df_copy['lvl2_first_attempt_ts'] = pd.to_datetime(df_copy['lvl2_first_attempt_ts'], errors='coerce')
    
    # Calculate time difference
    df_copy['rfh_to_fa_diff'] = (df_copy['lvl2_first_attempt_ts'] - df_copy['lvl1_REQUEST_FOR_HANDOVER_ts']).dt.total_seconds() / 86400
    
    # Remove nulls and negatives
    valid = df_copy[df_copy['rfh_to_fa_diff'].notna() & (df_copy['rfh_to_fa_diff'] >= 0)]['rfh_to_fa_diff']
    
    if len(valid) == 0:
        return np.nan
    
    return round(valid.median(), 2)


def calculate_rfh_to_fa_p90_lead_time(df):
    """
    RFH to FA P90 Lead Time (days)
    
    90th percentile of RFH to FA lead time
    
    Returns: float (P90 days)
    """
    if len(df) == 0:
        return np.nan
    
    df_copy = df.copy()
    
    # Parse timestamps if string
    if df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'].dtype == 'object':
        df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'] = pd.to_datetime(df_copy['lvl1_REQUEST_FOR_HANDOVER_ts'], errors='coerce')
    if df_copy['lvl2_first_attempt_ts'].dtype == 'object':
        df_copy['lvl2_first_attempt_ts'] = pd.to_datetime(df_copy['lvl2_first_attempt_ts'], errors='coerce')
    
    # Calculate time difference
    df_copy['rfh_to_fa_diff'] = (df_copy['lvl2_first_attempt_ts'] - df_copy['lvl1_REQUEST_FOR_HANDOVER_ts']).dt.total_seconds() / 86400
    
    # Remove nulls and negatives
    valid = df_copy[df_copy['rfh_to_fa_diff'].notna() & (df_copy['rfh_to_fa_diff'] >= 0)]['rfh_to_fa_diff']
    
    if len(valid) == 0:
        return np.nan
    
    return round(valid.quantile(0.9), 2)


def calculate_forward_sla_compliance(df):
    """
    Forward Delivery SLA Compliance (%)
    
    Formula: (Forward SLA met) / (Total forward journeys) * 100
    
    Field: forward_delivery_compliance == 'pass' (or YES/True)
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    forward_pass = df[df.get('forward_delivery_compliance', '') == 'pass'].shape[0]
    forward_pass += df[df.get('forward_delivery_compliance', '') == 'YES'].shape[0]
    forward_pass += df[df.get('forward_delivery_compliance', '') == True].shape[0]
    
    compliance = (forward_pass / len(df)) * 100
    return round(compliance, 2)


def calculate_forward_breach_percentage(df):
    """
    Forward Journey Closure SLA Breach (%)
    
    Formula: (Packages with forward SLA breach) / (Total packages) * 100
    
    Field: is_forward_hard_breach == 1 or is_forward_soft_breach == 1
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    # Count packages with any forward breach (hard or soft)
    breached = (
        ((df.get('is_forward_hard_breach', 0) == 1) | (df.get('is_forward_hard_breach', 0) == True)) |
        ((df.get('is_forward_soft_breach', 0) == 1) | (df.get('is_forward_soft_breach', 0) == True))
    ).sum()
    
    breach_pct = (breached / len(df)) * 100
    return round(breach_pct, 2)


def calculate_rts_breach_percentage(df):
    """
    RTS Journey Closure SLA Breach (%)
    
    Formula: (Packages with RTS SLA breach) / (RTS packages) * 100
    
    Field: is_rts_hard_breach == 1 or is_rts_soft_breach == 1
    
    Returns: float (0-100), or NaN if no RTS packages
    """
    # Filter to RTS packages only
    rts_df = df[df.get('final_status', '') == 'RETURNED']
    
    if len(rts_df) == 0:
        return np.nan
    
    # Count RTS breach
    breached = (
        ((rts_df.get('is_rts_hard_breach', 0) == 1) | (rts_df.get('is_rts_hard_breach', 0) == True)) |
        ((rts_df.get('is_rts_soft_breach', 0) == 1) | (rts_df.get('is_rts_soft_breach', 0) == True))
    ).sum()
    
    breach_pct = (breached / len(rts_df)) * 100
    return round(breach_pct, 2)


def calculate_e2e_breach_percentage(df):
    """
    E2E SLA Breach (%)
    
    Formula: (Any SLA breach: forward OR RTS) / (Total packages) * 100
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    # Any breach: forward breach OR RTS breach
    any_breach = (
        ((df.get('is_forward_hard_breach', 0) == 1) | (df.get('is_forward_hard_breach', 0) == True)) |
        ((df.get('is_forward_soft_breach', 0) == 1) | (df.get('is_forward_soft_breach', 0) == True)) |
        ((df.get('is_rts_hard_breach', 0) == 1) | (df.get('is_rts_hard_breach', 0) == True)) |
        ((df.get('is_rts_soft_breach', 0) == 1) | (df.get('is_rts_soft_breach', 0) == True))
    ).sum()
    
    breach_pct = (any_breach / len(df)) * 100
    return round(breach_pct, 2)


def calculate_failed_delivery_percentage(df):
    """
    Failed Delivery / FD (%)
    
    Formula: (Failed deliveries) / (Total delivery attempts) * 100
    
    Only counts packages that went through delivery (exclude in-transit, cancelled)
    
    Field: final_status in ['FAILED', 'DELIVERY_FAILED']
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    # Filter to packages that completed (delivered or failed)
    completed = df[df.get('final_status', '').isin(['DELIVERED', 'FAILED', 'DELIVERY_FAILED', 'RTS'])]
    
    if len(completed) == 0:
        return np.nan
    
    failed = completed[completed.get('final_status', '').isin(['FAILED', 'DELIVERY_FAILED'])].shape[0]
    
    fd_pct = (failed / len(completed)) * 100
    return round(fd_pct, 2)


def calculate_lost_percentage(df):
    """
    Lost (%)
    
    Formula: (Lost parcels) / (Total parcels) * 100
    
    Field: final_status == 'LOST'
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    lost = (df.get('final_status', '') == 'LOST').sum()
    
    lost_pct = (lost / len(df)) * 100
    return round(lost_pct, 2)


def calculate_damaged_percentage(df):
    """
    Damaged (%)
    
    Formula: (Damaged parcels) / (Total parcels) * 100
    
    Field: final_status == 'DAMAGED'
    
    Returns: float (0-100)
    """
    if len(df) == 0:
        return np.nan
    
    damaged = (df.get('final_status', '') == 'DAMAGED').sum()
    
    damaged_pct = (damaged / len(df)) * 100
    return round(damaged_pct, 2)


def color_code_kpi(value, kpi_name, target_values=None):
    """
    Assign color based on KPI value and targets.
    
    target_values: dict with 'target' and optional 'threshold' (yellow zone)
    
    Returns: 'green', 'yellow', or 'red'
    """
    if pd.isna(value):
        return 'gray'
    
    if target_values is None:
        # Default targets (can be overridden by Ralph)
        default_targets = {
            'Cost per Parcel (CPP)': {'target': 81.04, 'threshold': 85, 'inverse': True},  # Inverse: lower is better
            'Pickup Compliance (%)': {'target': 95, 'threshold': 85},
            'Forward Delivery SLA Compliance (%)': {'target': 95, 'threshold': 85},
            'Forward Journey Closure SLA Breach (%)': {'target': 5, 'threshold': 10, 'inverse': True},  # Inverse: lower is better
            'RTS Journey Closure SLA Breach (%)': {'target': 5, 'threshold': 10, 'inverse': True},
            'E2E SLA Breach (%)': {'target': 5, 'threshold': 10, 'inverse': True},
            'Failed Delivery/FD (%)': {'target': 2, 'threshold': 5, 'inverse': True},
            'Lost (%)': {'target': 0.5, 'threshold': 1, 'inverse': True},
            'Damaged (%)': {'target': 0.5, 'threshold': 1, 'inverse': True},
        }
        target_values = default_targets.get(kpi_name, {'target': None})
    
    if target_values.get('target') is None:
        return 'gray'
    
    target = target_values['target']
    threshold = target_values.get('threshold', target)
    is_inverse = target_values.get('inverse', False)  # Lower is better
    
    if is_inverse:
        # For metrics where lower is better (cost, breach %, failed %)
        if value <= target:
            return 'green'
        elif value <= threshold:
            return 'yellow'
        else:
            return 'red'
    else:
        # For metrics where higher is better (compliance %)
        if value >= target:
            return 'green'
        elif value >= threshold:
            return 'yellow'
        else:
            return 'red'


if __name__ == '__main__':
    print("KPI Calculator Module Loaded")
    print("Functions available:")
    print("- calculate_cpp()")
    print("- calculate_pickup_compliance()")
    print("- calculate_oc_to_rfh_lead_time()")
    print("- calculate_oc_to_fa_lead_time()")
    print("- calculate_rfh_to_fa_lead_time()")
    print("- calculate_rfh_to_fa_p90_lead_time()")
    print("- calculate_forward_sla_compliance()")
    print("- calculate_forward_breach_percentage()")
    print("- calculate_rts_breach_percentage()")
    print("- calculate_e2e_breach_percentage()")
    print("- calculate_failed_delivery_percentage()")
    print("- calculate_lost_percentage()")
    print("- calculate_damaged_percentage()")
    print("- color_code_kpi()")
