"""
Philippine Holiday Calendar 2026

Working days definition: Monday-Saturday (weekday 0-5), excluding:
- Sundays (weekday 6)
- 16 Philippine holidays
"""

from datetime import datetime, date, timedelta
from typing import List, Set

# Philippine Holidays in 2026 (16 total)
PH_HOLIDAYS_2026 = {
    date(2026, 1, 1),    # New Year's Day
    date(2026, 2, 9),    # EDSA People Power Revolution (Feb 9, Mon)
    date(2026, 2, 10),   # Special Non-Working Day (Day off for EDSA)
    date(2026, 2, 25),   # EDSA People Power Revolution (observed, Wed)
    date(2026, 4, 9),    # Day of Valor (Thu)
    date(2026, 4, 10),   # Good Friday (Fri)
    date(2026, 4, 11),   # Black Saturday (Sat) — already skip Sat
    date(2026, 4, 12),   # Easter Sunday (Sun) — already skip Sun
    date(2026, 4, 13),   # Easter Monday (Mon, special day off)
    date(2026, 6, 12),   # Independence Day (Fri)
    date(2026, 8, 21),   # Ninoy Aquino Day (Fri)
    date(2026, 11, 1),   # All Saints' Day (Sun) — already skip Sun
    date(2026, 11, 30),  # Bonifacio Day (Mon)
    date(2026, 12, 8),   # Feast of Immaculate Conception (Tue)
    date(2026, 12, 25),  # Christmas Day (Fri)
    date(2026, 12, 30),  # Rizal Day (Wed) — note: observed on Dec 30, not 31
    date(2026, 12, 31),  # New Year's Eve (special day off, Thu)
}

def is_working_day(dt: datetime) -> bool:
    """
    Check if a date is a working day.
    
    Working days: Monday-Saturday (not Sunday)
    Exclude: Philippine holidays
    
    Args:
        dt: datetime object to check
    
    Returns:
        True if working day, False if Sunday or holiday
    """
    d = dt.date() if isinstance(dt, datetime) else dt
    
    # Check if Sunday (weekday 6)
    if d.weekday() == 6:
        return False
    
    # Check if holiday
    if d in PH_HOLIDAYS_2026:
        return False
    
    return True


def add_working_days(start_dt: datetime, days: int) -> datetime:
    """
    Add N working days to a datetime, skipping Sundays and holidays.
    Target time: 23:59:59 on the final day.
    
    Args:
        start_dt: Starting datetime
        days: Number of working days to add
    
    Returns:
        Target datetime at 23:59:59 on the target working day
    """
    current = start_dt.date() if isinstance(start_dt, datetime) else start_dt
    working_days_added = 0
    
    # Start from the next day
    current += timedelta(days=1)
    
    # Count forward N working days
    while working_days_added < days:
        if is_working_day(datetime.combine(current, datetime.min.time())):
            working_days_added += 1
            if working_days_added == days:
                # Found the target day
                break
        current += timedelta(days=1)
    
    # Return at 23:59:59 on target day
    return datetime.combine(current, datetime.max.time())


def days_to_working_days(start_dt: datetime, end_dt: datetime) -> float:
    """
    Calculate the number of working days between two datetimes.
    
    Includes both start and end days if they are working days.
    
    Args:
        start_dt: Starting datetime
        end_dt: Ending datetime
    
    Returns:
        Number of working days (can be fractional for same-day or partial days)
    """
    current = start_dt.date() if isinstance(start_dt, datetime) else start_dt
    end = end_dt.date() if isinstance(end_dt, datetime) else end_dt
    
    working_days = 0.0
    
    while current <= end:
        if is_working_day(datetime.combine(current, datetime.min.time())):
            working_days += 1.0
        current += timedelta(days=1)
    
    return working_days


def sla_target_date(start_dt: datetime, sla_days: int) -> datetime:
    """
    Calculate SLA target date from a start datetime.
    
    Target: End of day (23:59:59) on the SLA_DAYS-th working day.
    
    Args:
        start_dt: Starting datetime (e.g., lvl1_IN_TRANSIT_ts)
        sla_days: SLA in working days
    
    Returns:
        Target datetime at 23:59:59 on the SLA target day
    """
    return add_working_days(start_dt, sla_days)


# ============================================================================
# TESTS
# ============================================================================

if __name__ == '__main__':
    print("Philippine Holiday Calendar 2026 - Unit Tests\n")
    
    # Test 1: is_working_day
    print("Test 1: is_working_day()")
    test_cases = [
        (datetime(2026, 5, 18), True, "Monday (May 18)"),
        (datetime(2026, 5, 19), True, "Tuesday (May 19)"),
        (datetime(2026, 5, 23), False, "Saturday (May 23)"),
        (datetime(2026, 5, 24), False, "Sunday (May 24)"),
        (datetime(2026, 1, 1), False, "New Year (Jan 1)"),
        (datetime(2026, 4, 10), False, "Good Friday (Apr 10)"),
    ]
    
    for dt, expected, label in test_cases:
        result = is_working_day(dt)
        status = "✓" if result == expected else "✗"
        print(f"  {status} {label}: {result} (expected {expected})")
    
    # Test 2: add_working_days
    print("\nTest 2: add_working_days()")
    base = datetime(2026, 5, 18, 9, 0)  # Monday May 18, 9:00 AM
    
    test_cases_add = [
        (1, date(2026, 5, 19), "1 day from Mon = Tue"),
        (2, date(2026, 5, 20), "2 days from Mon = Wed"),
        (5, date(2026, 5, 26), "5 days from Mon (skip Sat/Sun) = Tue"),
        (18, date(2026, 6, 9), "18 days from May 18 (long SLA)"),
    ]
    
    for days, expected_date, label in test_cases_add:
        result = add_working_days(base, days)
        result_date = result.date()
        status = "✓" if result_date == expected_date else "✗"
        time_str = result.strftime("%H:%M:%S")
        print(f"  {status} {label}: {result_date} {time_str} (expected {expected_date} 23:59:59)")
    
    # Test 3: sla_target_date (same as add_working_days)
    print("\nTest 3: sla_target_date() - GMA→GMA (2-day SLA)")
    base = datetime(2026, 5, 18, 9, 0)
    target = sla_target_date(base, 2)
    print(f"  Start: {base}")
    print(f"  SLA: 2 working days")
    print(f"  Target: {target} (should be May 20, 23:59:59)")
    
    print("\nTest 4: sla_target_date() - GMA→Luzon4 (18-day SLA)")
    target = sla_target_date(base, 18)
    print(f"  Start: {base}")
    print(f"  SLA: 18 working days")
    print(f"  Target: {target}")
    
    print("\n✅ All tests completed")
