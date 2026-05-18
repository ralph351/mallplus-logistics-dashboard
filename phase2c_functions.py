"""
Phase 2C: Breach Prediction Core Functions (Working-Day SLA Edition)

Based on SLA sheet structure:
- forward_delivery_sla (base SLA days)
- forward_journey_closure_soft_breach_sla (days to soft breach)
- forward_journey_closure_hard_breach_sla (days to hard breach)

All calculations skip Sundays and Philippine holidays (23:59:59 cutoff).
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from ph_holidays_2026 import is_working_day, add_working_days


def calculate_t3_forward_delivery_sla(
    order: Dict,
    sla_reference: Dict,
    current_time: Optional[datetime] = None
) -> Dict:
    """
    Calculate T3 (Forward Delivery SLA) with working-day logic.
    
    T3 = lvl1_IN_TRANSIT_ts → lvl2_first_attempt_ts
    
    Returns status: ON_TRACK, ON_TIME, SOFT_BREACH, HARD_BREACH, or BREACH (overdue without FA)
    """
    if current_time is None:
        current_time = datetime.now()
    
    route = (order['origin_region'], order['destination_region'])
    
    if route not in sla_reference:
        return {'status': 'ERROR', 'reason': f'Route {route} not in SLA reference'}
    
    sla_config = sla_reference[route]
    forward_delivery_sla_days = int(sla_config['forward_delivery_sla'])
    soft_breach_days = int(sla_config.get('forward_journey_closure_soft_breach_sla', 7))
    hard_breach_days = int(sla_config.get('forward_journey_closure_hard_breach_sla', 10))
    
    t3_start = order.get('lvl1_IN_TRANSIT_ts')
    t3_end = order.get('lvl2_first_attempt_ts')
    
    if t3_start is None:
        return {'status': 'NOT_IN_TRANSIT', 't3_remaining_days': None}
    
    # Calculate SLA target dates (working days only, 23:59:59)
    sla_target_dt = add_working_days(t3_start, forward_delivery_sla_days)
    soft_breach_dt = add_working_days(t3_start, soft_breach_days)
    hard_breach_dt = add_working_days(t3_start, hard_breach_days)
    
    if t3_end:
        # Journey complete
        elapsed_hours = (t3_end - t3_start).total_seconds() / 3600
        
        if t3_end <= sla_target_dt:
            status = 'ON_TIME'
        elif t3_end <= soft_breach_dt:
            status = 'SOFT_BREACH'
        elif t3_end <= hard_breach_dt:
            status = 'HARD_BREACH'
        else:
            status = 'HARD_BREACH'  # Still hard breach, just more severe
        
        t3_remaining_days = 0  # Journey done
    else:
        # Journey in progress
        elapsed_hours = (current_time - t3_start).total_seconds() / 3600
        
        if current_time <= sla_target_dt:
            status = 'ON_TRACK'
            t3_remaining_days = (sla_target_dt - current_time).total_seconds() / 3600 / 24.0
        else:
            status = 'BREACH'  # Overdue but no FA recorded
            t3_remaining_days = (sla_target_dt - current_time).total_seconds() / 3600 / 24.0  # negative
    
    return {
        'status': status,
        'elapsed_hours': elapsed_hours,
        't3_remaining_days': t3_remaining_days,
        'sla_target_datetime': sla_target_dt,
        'soft_breach_datetime': soft_breach_dt,
        'hard_breach_datetime': hard_breach_dt,
        'is_complete': t3_end is not None
    }


def determine_current_phase(order: Dict) -> str:
    """Determine which micro-phase the package is in."""
    phase_map = {
        'mp1': 'lvl2_domestic_ib_success_first_mile_hub_ts',
        'mp2': 'lvl2_domestic_ob_success_first_mile_hub_ts',
        'mp3': 'lvl2_domestic_ib_success_in_sort_center_ts',
        'mp4': 'lvl2_domestic_ob_success_in_sort_center_ts',
        'mp5': 'lvl2_domestic_package_stationed_in_ts',
        'mp6': 'lvl2_domestic_package_stationed_out_ts',
        'mp7': 'lvl2_first_attempt_ts'
    }
    
    for phase, ts_field in phase_map.items():
        if order.get(ts_field) is None:
            return phase
    
    return 'DELIVERED'


def get_actual_phase_duration_hours(order: Dict, phase_id: str) -> Optional[float]:
    """Get actual duration of a micro-phase in hours."""
    phase_transitions = {
        'mp1': ('lvl1_IN_TRANSIT_ts', 'lvl2_domestic_ib_success_first_mile_hub_ts'),
        'mp2': ('lvl2_domestic_ib_success_first_mile_hub_ts', 'lvl2_domestic_ob_success_first_mile_hub_ts'),
        'mp3': ('lvl2_domestic_ob_success_first_mile_hub_ts', 'lvl2_domestic_ib_success_in_sort_center_ts'),
        'mp4': ('lvl2_domestic_ib_success_in_sort_center_ts', 'lvl2_domestic_ob_success_in_sort_center_ts'),
        'mp5': ('lvl2_domestic_ob_success_in_sort_center_ts', 'lvl2_domestic_package_stationed_in_ts'),
        'mp6': ('lvl2_domestic_package_stationed_in_ts', 'lvl2_domestic_package_stationed_out_ts'),
        'mp7': ('lvl2_domestic_package_stationed_out_ts', 'lvl2_first_attempt_ts')
    }
    
    if phase_id not in phase_transitions:
        return None
    
    start_field, end_field = phase_transitions[phase_id]
    start_ts = order.get(start_field)
    end_ts = order.get(end_field)
    
    if start_ts is None:
        return None
    
    if end_ts is None:
        end_ts = datetime.now()
    
    return max(0, (end_ts - start_ts).total_seconds() / 3600)


def detect_bottlenecks_per_phase(order: Dict, mp_baselines: Dict) -> List[Dict]:
    """Detect phases that exceeded P90 baseline."""
    route = (order['origin_region'], order['destination_region'])
    
    if route not in mp_baselines:
        return []
    
    baseline = mp_baselines[route]
    bottlenecks = []
    
    for phase_id in ['mp1', 'mp2', 'mp3', 'mp4', 'mp5', 'mp6', 'mp7']:
        actual = get_actual_phase_duration_hours(order, phase_id)
        p90_key = f'{phase_id}_p90_hours'
        
        if actual is None or p90_key not in baseline:
            continue
        
        p90 = baseline[p90_key]
        
        if actual > p90:
            excess = actual - p90
            excess_pct = (excess / p90 * 100) if p90 > 0 else 0
            
            if excess > p90 * 2:
                severity = 'CRITICAL'
            elif excess > p90:
                severity = 'HIGH'
            elif excess > p90 * 0.5:
                severity = 'MEDIUM'
            else:
                severity = 'MINOR'
            
            bottlenecks.append({
                'phase': phase_id,
                'actual_hours': actual,
                'p90_hours': p90,
                'excess_hours': excess,
                'excess_percent': excess_pct,
                'severity': severity
            })
    
    return bottlenecks


def calculate_complete_buffer(
    order: Dict,
    sla_reference: Dict,
    mp_baselines: Dict,
    current_time: Optional[datetime] = None
) -> Dict:
    """
    Calculate buffer = SLA_remaining - time_required_for_remaining_phases.
    
    For completed: buffer = how many days early/late
    For in-progress: buffer = remaining SLA time - time needed to finish
    """
    if current_time is None:
        current_time = datetime.now()
    
    route = (order['origin_region'], order['destination_region'])
    
    if route not in mp_baselines or route not in sla_reference:
        return {'buffer_days': None, 'risk_tier': 'UNKNOWN'}
    
    t3_info = calculate_t3_forward_delivery_sla(order, sla_reference, current_time)
    
    if t3_info.get('status') == 'NOT_IN_TRANSIT':
        return {'buffer_days': None, 'risk_tier': 'UNKNOWN'}
    
    # **CASE 1: Delivery Complete**
    if t3_info['is_complete']:
        sla_days = int(sla_reference[route]['forward_delivery_sla'])
        sla_hours = sla_days * 24
        actual_hours = t3_info['elapsed_hours']
        buffer_hours = sla_hours - actual_hours
        buffer_days = buffer_hours / 24.0
        
        # Risk tier based on breach status
        if t3_info['status'] == 'ON_TIME':
            risk_tier = 'LOW'
        elif t3_info['status'] == 'SOFT_BREACH':
            risk_tier = 'MEDIUM'
        elif t3_info['status'] == 'HARD_BREACH':
            risk_tier = 'CRITICAL'
        else:
            risk_tier = 'CRITICAL'
    
    # **CASE 2: Delivery In Progress**
    else:
        current_phase = determine_current_phase(order)
        baseline = mp_baselines[route]
        
        # Calculate time required for remaining phases
        time_required = 0.0
        
        # If in a phase, estimate time to complete it
        if current_phase != 'DELIVERED':
            actual = get_actual_phase_duration_hours(order, current_phase)
            p90_key = f'{current_phase}_p90_hours'
            
            if p90_key in baseline:
                p90 = baseline[p90_key]
                if actual and actual > p90:
                    # Already over P90
                    time_required += actual - p90 + p90 * 0.2
                else:
                    # Need remaining time
                    time_required += max(0, p90 - (actual or 0))
        
        # Add remaining phases
        phases = ['mp1', 'mp2', 'mp3', 'mp4', 'mp5', 'mp6', 'mp7']
        current_idx = phases.index(current_phase) if current_phase in phases else 0
        
        for phase in phases[current_idx + 1:]:
            p90_key = f'{phase}_p90_hours'
            if p90_key in baseline:
                time_required += baseline[p90_key]
        
        # Buffer = remaining SLA time - time needed
        remaining_hours = t3_info['t3_remaining_days'] * 24 if t3_info['t3_remaining_days'] else 0
        buffer_hours = remaining_hours - time_required
        buffer_days = buffer_hours / 24.0
        
        # Risk tier based on buffer
        if buffer_days > 1.0:
            risk_tier = 'LOW'
        elif buffer_days > 0:
            risk_tier = 'MEDIUM'
        elif buffer_days > -1.0:
            risk_tier = 'HIGH'
        else:
            risk_tier = 'CRITICAL'
    
    return {
        'buffer_days': buffer_days,
        'buffer_hours': buffer_hours,
        't3_remaining_days': t3_info['t3_remaining_days'],
        'risk_tier': risk_tier,
        't3_status': t3_info['status']
    }


def analyze_order(
    order: Dict,
    sla_reference: Dict,
    mp_baselines: Dict,
    current_time: Optional[datetime] = None
) -> Dict:
    """Complete analysis: T3 + buffer + bottlenecks + risk tier."""
    if current_time is None:
        current_time = datetime.now()
    
    t3 = calculate_t3_forward_delivery_sla(order, sla_reference, current_time)
    buffer = calculate_complete_buffer(order, sla_reference, mp_baselines, current_time)
    bottlenecks = detect_bottlenecks_per_phase(order, mp_baselines)
    
    return {
        'tracking': order.get('tracking_number'),
        'route': f"{order.get('origin_region')} → {order.get('destination_region')}",
        't3_status': t3.get('status'),
        't3_remaining_days': t3.get('t3_remaining_days'),
        'buffer_days': buffer.get('buffer_days'),
        'risk_tier': buffer.get('risk_tier'),
        'bottlenecks': bottlenecks,
        'current_phase': determine_current_phase(order)
    }
