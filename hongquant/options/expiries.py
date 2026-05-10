"""Option expiration date utilities. No I/O — pure date arithmetic."""
from __future__ import annotations

from datetime import date, timedelta


def front_friday(today: date) -> date:
    """Return the coming Friday (or today if today is Friday)."""
    days_until = (4 - today.weekday()) % 7
    return today + timedelta(days=days_until)


def next_friday(today: date) -> date:
    """Return the Friday after the front Friday."""
    return front_friday(today) + timedelta(weeks=1)


def monthly_opex(year: int, month: int) -> date:
    """Return the third Friday of the given month (standard monthly options expiration)."""
    d = date(year, month, 1)
    days_until_first_friday = (4 - d.weekday()) % 7
    first_friday = d + timedelta(days=days_until_first_friday)
    return first_friday + timedelta(weeks=2)


def triple_witching(year: int, quarter: int) -> date:
    """Return the triple witching date for the given quarter (1=Q1, 2=Q2, 3=Q3, 4=Q4).

    Triple witching is the third Friday of March, June, September, or December.
    """
    if quarter not in (1, 2, 3, 4):
        raise ValueError(f"quarter must be 1-4, got {quarter}")
    month_map = {1: 3, 2: 6, 3: 9, 4: 12}
    return monthly_opex(year, month_map[quarter])


def expiries_within(today: date, days: int) -> list[date]:
    """Return all weekly Friday expiration dates from front_friday to today + days."""
    result: list[date] = []
    d = front_friday(today)
    end = today + timedelta(days=days)
    while d <= end:
        result.append(d)
        d += timedelta(weeks=1)
    return result


def is_opex_week(today: date) -> bool:
    """Return True if the front Friday is a monthly OpEx (third Friday of its month)."""
    ff = front_friday(today)
    return ff == monthly_opex(ff.year, ff.month)


def is_triple_witching_week(today: date) -> bool:
    """Return True if the front Friday is a quarterly triple witching date."""
    ff = front_friday(today)
    if ff.month not in (3, 6, 9, 12):
        return False
    quarter_map = {3: 1, 6: 2, 9: 3, 12: 4}
    return ff == triple_witching(ff.year, quarter_map[ff.month])
