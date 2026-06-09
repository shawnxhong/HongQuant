"""Pillar A — Extension / potential energy (design §2 Pillar A).

How far, how steep, how one-sided the trend has run. Slow grinds don't flash-
crash; vertical, accelerating, overbought moves do. Every feature is ranked
against the instrument's own trailing history (a +20% gap above the 200dma means
different things for gold and for NVDA), then combined into a 0-1 sub-score.

Reuses the pure factor functions in ``hongquant/factors/equity.py``.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..factors import equity as f
from .normalize import pct_rank, scale_unit, weighted_mean
from .types import PillarScore

_WEIGHTS = {
    "dist_200dma": 0.25,
    "dist_50dma": 0.20,
    "ret_20d": 0.20,
    "ret_60d": 0.10,
    "rsi": 0.10,
    "acceleration": 0.10,
    "consec_up": 0.05,
}


def _consecutive_up_days(closes: pd.Series) -> int:
    diffs = closes.diff().dropna()
    count = 0
    for v in reversed(diffs.to_numpy()):
        if v > 0:
            count += 1
        else:
            break
    return count


def _acceleration(closes: pd.Series, span: int = 5) -> pd.Series:
    """Change in trailing ``span``-day return — proxy for parabolic acceleration."""
    ret = closes.pct_change(span)
    return ret - ret.shift(span)


def compute(closes: pd.Series | None) -> PillarScore:
    """Compute the Extension pillar (0-1) from a daily close series."""
    if closes is None or len(closes.dropna()) < 60:
        return PillarScore(value=None, reasons=["Pillar A: insufficient price history"])

    closes = closes.dropna()
    d50 = f.distance_from_sma(closes, 50)
    d200 = f.distance_from_sma(closes, 200)
    ret20 = f.pct_return(closes, 20)
    ret60 = f.pct_return(closes, 60)
    rsi = f.rsi(closes, 14)
    accel = _acceleration(closes)
    consec = _consecutive_up_days(closes)

    parts: dict[str, float | None] = {
        "dist_200dma": pct_rank(d200),
        "dist_50dma": pct_rank(d50),
        "ret_20d": pct_rank(ret20),
        "ret_60d": pct_rank(ret60),
        "rsi": scale_unit(float(rsi.iloc[-1]) if not np.isnan(rsi.iloc[-1]) else float("nan"), 50.0, 90.0),
        "acceleration": pct_rank(accel),
        "consec_up": scale_unit(float(consec), 2.0, 8.0),
    }

    value = weighted_mean(parts, _WEIGHTS)

    reasons: list[str] = []
    d200_last = float(d200.iloc[-1]) if not np.isnan(d200.iloc[-1]) else float("nan")
    if not np.isnan(d200_last) and (parts["dist_200dma"] or 0) > 0.85:
        reasons.append(f"{d200_last:+.0%} vs 200dma — {parts['dist_200dma']:.0%} of own history")
    if (parts["acceleration"] or 0) > 0.85:
        reasons.append("trend is accelerating (parabolic stretch)")
    if not np.isnan(rsi.iloc[-1]) and rsi.iloc[-1] > 75:
        reasons.append(f"RSI {rsi.iloc[-1]:.0f} — overbought")
    if consec >= 6:
        reasons.append(f"{consec} consecutive up days — one-sided")

    clean = {k: v for k, v in parts.items() if v is not None and not np.isnan(v)}
    return PillarScore(value=value, features=clean, reasons=reasons)
