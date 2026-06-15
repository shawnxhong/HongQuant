"""Pure transform primitives for LRM composites (spec §3 note, §4.1).

Sign convention: every signed_transform is oriented so that POSITIVE = liquidity
expansion / risk-on. The composite applies a per-component ``sign`` to enforce
this. All functions are point-in-time — they read only the trailing window
ending at the latest observation and never look ahead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def delta(series: pd.Series, periods: int) -> pd.Series:
    """N-period difference (Δ): series - series.shift(N)."""
    return series - series.shift(periods)


def pct_change(series: pd.Series, periods: int) -> pd.Series:
    """N-period percent change."""
    return series.pct_change(periods)


def apply_op(series: pd.Series, op: str, periods: int) -> pd.Series:
    """Apply a composite component's transform op to its raw series."""
    if op == "delta":
        return delta(series, periods)
    if op == "pct_change":
        return pct_change(series, periods)
    if op == "level":
        return series
    raise ValueError(f"unknown transform op: {op!r}")


def rolling_z(
    series: pd.Series,
    *,
    window: int,
    min_periods: int,
    clip: float = 2.0,
) -> float:
    """Standard z-score of the latest value vs its trailing window, clipped.

    Uses the most recent ``window`` observations (or all available if fewer, as
    long as there are at least ``min_periods`` — spec's "最少 3 年否则用全样本").
    Returns NaN if there is too little history or zero dispersion.
    """
    s = series.dropna()
    if len(s) < min_periods:
        return float("nan")
    w = s.tail(window)
    mu = float(w.mean())
    sd = float(w.std(ddof=0))
    if not np.isfinite(sd) or sd == 0:
        return float("nan")
    z = (float(w.iloc[-1]) - mu) / sd
    return float(np.clip(z, -clip, clip))


def percentile(series: pd.Series, *, window: int, min_periods: int) -> float:
    """Percentile (0-1) of the latest value within its trailing window."""
    s = series.dropna()
    if len(s) < min_periods:
        return float("nan")
    w = s.tail(window)
    return float((w <= w.iloc[-1]).mean())
