"""Normalization primitives — relative to each instrument's own history.

"Crowding" / "extension" are *relative* concepts: NVDA's stretched is not gold's
stretched. So almost every raw feature is converted to a percentile or robust
z-score against that instrument's own trailing 1-3y window, winsorized to tame
outliers. Pure numpy/pandas — no scipy/sklearn.

All functions are point-in-time: they read only the trailing window ending at
the latest observation and never look ahead.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

DEFAULT_WINDOW = 504        # ~2 trading years
DEFAULT_MIN_PERIODS = 60    # need at least a quarter of data to rank


def winsorize(s: pd.Series, lower: float = 0.02, upper: float = 0.98) -> pd.Series:
    """Clip a series to its [lower, upper] quantiles."""
    s = s.dropna()
    if s.empty:
        return s
    lo, hi = s.quantile(lower), s.quantile(upper)
    return s.clip(lo, hi)


def pct_rank(
    series: pd.Series,
    *,
    window: int = DEFAULT_WINDOW,
    winsor: float = 0.02,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> float:
    """Percentile (0-1) of the latest value within its trailing window.

    The window is winsorized before ranking so a single spike does not compress
    every other observation. Returns NaN if there is too little history.
    1.0 means the latest value is at/above its historical extreme.
    """
    s = series.dropna()
    if len(s) < min_periods:
        return float("nan")
    w = s.tail(window)
    lo, hi = w.quantile(winsor), w.quantile(1.0 - winsor)
    if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
        return 0.5
    wc = w.clip(lo, hi)
    x = float(min(max(w.iloc[-1], lo), hi))
    return float((wc <= x).mean())


def robust_z(
    series: pd.Series,
    *,
    window: int = DEFAULT_WINDOW,
    clip: float = 3.0,
    min_periods: int = DEFAULT_MIN_PERIODS,
) -> float:
    """Robust z-score of the latest value: (x - median) / (1.4826 * MAD), clipped."""
    s = series.dropna()
    if len(s) < min_periods:
        return float("nan")
    w = s.tail(window)
    med = float(w.median())
    mad = float((w - med).abs().median())
    if mad <= 0:
        return 0.0
    z = (float(w.iloc[-1]) - med) / (1.4826 * mad)
    return float(np.clip(z, -clip, clip))


def z_to_unit(z: float, *, clip: float = 3.0) -> float:
    """Map a clipped z-score in [-clip, clip] to [0, 1]."""
    if z is None or (isinstance(z, float) and math.isnan(z)):
        return float("nan")
    return float(np.clip((z / clip + 1.0) / 2.0, 0.0, 1.0))


def scale_unit(value: float, lo: float, hi: float) -> float:
    """Linearly map ``value`` from [lo, hi] to [0, 1] with clamping.

    For threshold-style features measured on a fixed scale (e.g. a term-structure
    ratio) rather than relative to history.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)) or hi == lo:
        return float("nan")
    return float(np.clip((value - lo) / (hi - lo), 0.0, 1.0))


def weighted_mean(
    parts: dict[str, float | None], weights: dict[str, float]
) -> float | None:
    """Weighted mean over the available (non-NaN) parts, renormalizing weights.

    Returns None if no part is available — lets a pillar degrade gracefully when
    a data source is missing rather than silently scoring zero.
    """
    num = 0.0
    den = 0.0
    for key, w in weights.items():
        v = parts.get(key)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            continue
        num += w * v
        den += w
    if den == 0:
        return None
    return num / den
