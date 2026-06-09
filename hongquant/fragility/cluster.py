"""Theme-cluster correlation cascade detector (design §2, original feature #2).

When a group of names (all AI semis, or EWY with Samsung/Hynix) starts moving
as one, a shock to any single member cascades to the whole cluster. Rising
within-cluster return correlation is therefore a systemic-fragility signal for
that theme. We measure each cluster's mean pairwise rolling correlation and how
extreme it is versus the cluster's own history.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .normalize import pct_rank

DEFAULT_WINDOW = 20


def daily_returns(closes_by_symbol: dict[str, pd.Series]) -> pd.DataFrame:
    """Align per-symbol close series on common dates and return daily pct returns."""
    frames = {sym: s for sym, s in closes_by_symbol.items() if s is not None and len(s) > 1}
    if len(frames) < 2:
        return pd.DataFrame()
    wide = pd.DataFrame(frames).sort_index()
    return wide.pct_change().dropna(how="all")


def mean_pairwise_corr_series(returns: pd.DataFrame, *, window: int = DEFAULT_WINDOW) -> pd.Series:
    """Time series of the mean off-diagonal pairwise correlation across columns.

    For each date, the rolling-``window`` correlation matrix of the columns is
    averaged over its off-diagonal entries. Returns an empty Series for < 2
    columns or insufficient history.
    """
    cols = list(returns.columns)
    if len(cols) < 2 or len(returns) < window:
        return pd.Series(dtype=float)

    rolling_corr = returns.rolling(window).corr()
    n = len(cols)
    off_diag = ~np.eye(n, dtype=bool)

    out: dict[pd.Timestamp, float] = {}
    for dt, block in rolling_corr.groupby(level=0):
        mat = block.droplevel(0).reindex(index=cols, columns=cols).to_numpy()
        vals = mat[off_diag]
        vals = vals[np.isfinite(vals)]
        if vals.size:
            out[dt] = float(vals.mean())
    return pd.Series(out).sort_index()


def cluster_signal(
    closes_by_symbol: dict[str, pd.Series],
    *,
    window: int = DEFAULT_WINDOW,
) -> tuple[float | None, float | None]:
    """Return (latest mean pairwise correlation, its percentile vs own history).

    The percentile is the fragility-relevant number: a cluster that is *unusually*
    correlated right now is primed to cascade. Returns (None, None) when a
    cluster is too small or too short to evaluate.
    """
    rets = daily_returns(closes_by_symbol)
    if rets.empty:
        return None, None
    series = mean_pairwise_corr_series(rets, window=window)
    if series.empty:
        return None, None
    latest = float(series.iloc[-1])
    pctile = pct_rank(series, min_periods=window * 2)
    if np.isnan(pctile):
        pctile = None
    return latest, pctile
