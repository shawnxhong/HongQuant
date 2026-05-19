"""Equity / ETF factor functions.

All functions take a pandas Series of close prices indexed by date and return
a Series of the same length (NaN where insufficient history). Pure -- no I/O.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def pct_return(close: pd.Series, n: int) -> pd.Series:
    """N-bar percent return: close[t] / close[t-n] - 1."""
    return close.pct_change(n)


def sma(close: pd.Series, n: int) -> pd.Series:
    """N-bar simple moving average."""
    return close.rolling(n, min_periods=n).mean()


def distance_from_sma(close: pd.Series, n: int) -> pd.Series:
    """Fractional distance of close above (positive) or below (negative) its N-bar SMA."""
    ma = sma(close, n)
    return close / ma - 1.0


def rolling_high(close: pd.Series, n: int) -> pd.Series:
    """Rolling N-bar maximum of close."""
    return close.rolling(n, min_periods=n).max()


def distance_from_high(close: pd.Series, n: int) -> pd.Series:
    """Fractional distance below the rolling N-bar high. Always <= 0 (or NaN)."""
    high = rolling_high(close, n)
    return close / high - 1.0


def drawdown_from_peak(close: pd.Series, n: int) -> pd.Series:
    """Current drawdown from the trailing-N-bar peak (alias of distance_from_high)."""
    return distance_from_high(close, n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder's RSI(n). First n bars are NaN.

    When avg_loss is 0 (monotone up) division yields inf and RSI -> 100; when
    both averages are 0 (flat) RSI is NaN -- both behaviors are standard.
    """
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    avg_loss = loss.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
    return 100.0 - 100.0 / (1.0 + rs)
