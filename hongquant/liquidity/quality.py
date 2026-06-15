"""Data-quality rules: fill policy, staleness budgets, parse-failure logging.

Spec §3 data-quality rule: daily series may be forward-filled ≤5 trading days;
monthly/quarterly series must NOT be filled across publication periods; any
composite component older than its staleness budget is dropped and the remaining
weights renormalize (handled in composites.py).
"""
from __future__ import annotations

import pandas as pd

from ..logging import logger

DAILY_FFILL_LIMIT = 5  # trading days


def forward_fill(series: pd.Series, frequency: str, *, limit: int = DAILY_FFILL_LIMIT) -> pd.Series:
    """Forward-fill per the fill policy: daily up to ``limit``; never for lower freq."""
    if series.empty:
        return series
    if frequency == "daily":
        return series.ffill(limit=limit)
    return series  # weekly/monthly/quarterly: no cross-period fill


def staleness_budget(key: str, budgets: dict[str, int]) -> int:
    """Budget in days for a component key, falling back to ``default``."""
    return int(budgets.get(key, budgets.get("default", 10)))


def is_stale(staleness: int | None, budget_days: int) -> bool:
    """True if a component is missing or older than its budget."""
    return staleness is None or staleness > budget_days


def log_parse_failure(source: str, detail: str) -> None:
    """Single chokepoint for scraper/parse failures so the system never degrades silently."""
    logger.warning("LRM parse-failure [{}]: {}", source, detail)
