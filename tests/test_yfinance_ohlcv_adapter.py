from __future__ import annotations

import sys
import types

import pandas as pd

from hongquant.data.adapters.yfinance_ import fetch_ohlcv


def test_yfinance_single_ticker_multiindex_columns(monkeypatch):
    idx = pd.date_range("2026-06-01", periods=3, freq="D")
    cols = pd.MultiIndex.from_product([["SPY"], ["Open", "High", "Low", "Close", "Volume"]])
    raw = pd.DataFrame(
        [
            [100.0, 101.0, 99.0, 100.5, 1000],
            [101.0, 102.0, 100.0, 101.5, 1100],
            [102.0, 103.0, 101.0, 102.5, 1200],
        ],
        index=idx,
        columns=cols,
    )

    def fake_download(**kwargs):
        return raw

    monkeypatch.setitem(sys.modules, "yfinance", types.SimpleNamespace(download=fake_download))

    df = fetch_ohlcv(["SPY"], start="2026-06-01", interval="1d")

    assert len(df) == 3
    assert df["symbol"].unique().tolist() == ["SPY"]
    assert df["close"].tolist() == [100.5, 101.5, 102.5]
    assert df["source"].unique().tolist() == ["yfinance"]
