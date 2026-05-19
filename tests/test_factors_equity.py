from __future__ import annotations

import numpy as np
import pandas as pd

from hongquant.factors.equity import (
    distance_from_high,
    distance_from_sma,
    drawdown_from_peak,
    pct_return,
    rolling_high,
    rsi,
    sma,
)


def _dates(n: int) -> pd.DatetimeIndex:
    return pd.date_range("2026-01-01", periods=n, freq="B")


def test_pct_return_basic():
    close = pd.Series([100, 110, 121], index=_dates(3))
    out = pct_return(close, 1)
    assert np.isnan(out.iloc[0])
    assert out.iloc[1] == pytest_approx(0.10)
    assert out.iloc[2] == pytest_approx(0.10)


def test_pct_return_multi_period():
    close = pd.Series([100, 110, 121, 100], index=_dates(4))
    out = pct_return(close, 3)
    assert np.isnan(out.iloc[2])
    assert out.iloc[3] == pytest_approx(0.0)


def test_sma_matches_rolling_mean():
    close = pd.Series([1, 2, 3, 4, 5, 6], index=_dates(6), dtype=float)
    out = sma(close, 3)
    assert np.isnan(out.iloc[0])
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest_approx(2.0)
    assert out.iloc[5] == pytest_approx(5.0)


def test_distance_from_sma_sign_and_magnitude():
    close = pd.Series([10, 10, 10, 11], index=_dates(4), dtype=float)
    out = distance_from_sma(close, 3)
    # SMA at idx 3 = (10+10+11)/3 = 10.333...
    # distance = 11/10.333 - 1 = 0.0645
    assert out.iloc[3] == pytest_approx(0.0645161290, rel=1e-6)


def test_rolling_high_picks_max():
    close = pd.Series([1, 5, 3, 8, 2, 7], index=_dates(6), dtype=float)
    out = rolling_high(close, 3)
    assert np.isnan(out.iloc[1])
    assert out.iloc[2] == 5.0
    assert out.iloc[3] == 8.0
    assert out.iloc[4] == 8.0
    assert out.iloc[5] == 8.0


def test_distance_from_high_monotonic_up_returns_zero_at_top():
    close = pd.Series(np.linspace(100, 200, 10), index=_dates(10))
    out = distance_from_high(close, 10)
    assert out.iloc[-1] == pytest_approx(0.0)
    # Series is non-positive
    assert (out.dropna() <= 1e-12).all()


def test_drawdown_from_peak_20pct_drop():
    # Climb to 100, drop to 80 -> drawdown -20%
    series = [*range(50, 101, 5), 80]
    close = pd.Series(series, index=_dates(len(series)), dtype=float)
    out = drawdown_from_peak(close, len(series))
    assert out.iloc[-1] == pytest_approx(-0.20)


def test_rsi_uptrend_above_70():
    # Strict monotone increase -> RSI saturates at 100
    close = pd.Series(np.arange(1, 50, dtype=float), index=_dates(49))
    out = rsi(close, 14)
    assert out.dropna().iloc[-1] > 70.0


def test_rsi_downtrend_below_30():
    close = pd.Series(np.arange(50, 1, -1, dtype=float), index=_dates(49))
    out = rsi(close, 14)
    assert out.dropna().iloc[-1] < 30.0


def test_rsi_first_n_bars_are_nan():
    close = pd.Series(np.arange(1, 30, dtype=float), index=_dates(29))
    out = rsi(close, 14)
    assert out.iloc[:13].isna().all()


def test_short_series_returns_nan():
    close = pd.Series([100.0, 101.0], index=_dates(2))
    assert sma(close, 5).isna().all()
    assert distance_from_sma(close, 5).isna().all()
    assert distance_from_high(close, 5).isna().all()


# small custom approx wrapper to keep the file pytest-fixture-free
def pytest_approx(value, rel=1e-9, abs=1e-9):
    import pytest

    return pytest.approx(value, rel=rel, abs=abs)
