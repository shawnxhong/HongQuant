"""Momentum fragility signals: relative strength and breadth."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd


def _fetch_closes(tickers: list[str], window: int) -> pd.DataFrame:
    """Fetch daily closes via yfinance for the last `window` trading days."""
    import yfinance as yf  # lazy import

    end = datetime.now(tz=UTC)
    start = end - timedelta(days=window * 2 + 10)  # buffer for weekends/holidays
    data = yf.download(
        tickers,
        start=start.date().isoformat(),
        end=end.date().isoformat(),
        progress=False,
        auto_adjust=True,
    )
    if isinstance(data.columns, pd.MultiIndex):
        closes = data["Close"]
    else:
        closes = data[["Close"]] if "Close" in data.columns else data
    return closes.dropna(how="all").tail(window)


def relative_strength(symbol_a: str, symbol_b: str, *, window: int = 5) -> float:
    """5-day return of A minus 5-day return of B.

    Positive = A outperforming B; negative = A underperforming.
    """
    closes = _fetch_closes([symbol_a, symbol_b], window + 1)
    if symbol_a not in closes.columns or symbol_b not in closes.columns:
        return float("nan")
    if len(closes) < 2:
        return float("nan")
    ret_a = float(closes[symbol_a].iloc[-1] / closes[symbol_a].iloc[0] - 1)
    ret_b = float(closes[symbol_b].iloc[-1] / closes[symbol_b].iloc[0] - 1)
    return ret_a - ret_b


def breadth(watchlist: list[str], *, window_short: int = 20, window_long: int = 50) -> dict:
    """Compute momentum breadth for the watchlist.

    Returns:
        pct_above_20dma: fraction above 20-day moving average
        pct_above_50dma: fraction above 50-day moving average
        advancers_5d: count with positive 5-day return
        decliners_5d: count with negative 5-day return
    """
    if not watchlist:
        return {"pct_above_20dma": float("nan"), "pct_above_50dma": float("nan"),
                "advancers_5d": 0, "decliners_5d": 0}

    closes = _fetch_closes(watchlist, window_long + 10)
    if closes.empty:
        return {"pct_above_20dma": float("nan"), "pct_above_50dma": float("nan"),
                "advancers_5d": 0, "decliners_5d": 0}

    valid = [t for t in watchlist if t in closes.columns]
    above_20 = above_50 = adv = dec = 0

    for ticker in valid:
        s = closes[ticker].dropna()
        if len(s) < 6:
            continue
        spot = s.iloc[-1]
        if len(s) >= window_short and spot > s.iloc[-window_short:].mean():
            above_20 += 1
        if len(s) >= window_long and spot > s.iloc[-window_long:].mean():
            above_50 += 1
        ret_5d = spot / s.iloc[-6] - 1 if len(s) >= 6 else float("nan")
        if not np.isnan(ret_5d):
            if ret_5d > 0:
                adv += 1
            else:
                dec += 1

    n = len(valid)
    return {
        "pct_above_20dma": above_20 / n if n else float("nan"),
        "pct_above_50dma": above_50 / n if n else float("nan"),
        "advancers_5d": adv,
        "decliners_5d": dec,
    }


def momentum_fragility_score(
    *,
    qqq_spy_rs: float,
    smh_qqq_rs: float,
    pct_above_20dma: float,
    vix_5d_change: float,
) -> float:
    """Composite 0-1 momentum fragility score.

    Higher = more fragile (bad for momentum longs).
    Inputs are all fractions (e.g. -0.02 = -2%).
    """
    score = 0.0
    weight_sum = 0.0

    # QQQ underperforming SPY (negative rs = tech weakening)
    if not np.isnan(qqq_spy_rs):
        # rs of -3% or worse → 1.0; +2% or better → 0.0
        qqq_norm = float(np.clip((-qqq_spy_rs) / 0.03, 0, 1))
        score += qqq_norm * 0.35
        weight_sum += 0.35

    # SMH underperforming QQQ (semiconductors leading the weakness)
    if not np.isnan(smh_qqq_rs):
        smh_norm = float(np.clip((-smh_qqq_rs) / 0.03, 0, 1))
        score += smh_norm * 0.30
        weight_sum += 0.30

    # Low breadth (few stocks above 20dma → momentum narrowing)
    if not np.isnan(pct_above_20dma):
        # below 40% → 1.0; above 70% → 0.0
        breadth_norm = float(np.clip((0.70 - pct_above_20dma) / 0.30, 0, 1))
        score += breadth_norm * 0.20
        weight_sum += 0.20

    # VIX rising (5d change > 0 → rising fear)
    if not np.isnan(vix_5d_change):
        # +25% vix rise or more → 1.0; flat or negative → 0.0
        vix_norm = float(np.clip(vix_5d_change / 0.25, 0, 1))
        score += vix_norm * 0.15
        weight_sum += 0.15

    return float(score / weight_sum) if weight_sum > 0 else 0.0
