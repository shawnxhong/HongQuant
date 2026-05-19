from __future__ import annotations

import sys
import types
from datetime import date

import pandas as pd

from hongquant.options.adapters.polygon_options import CHAIN_COLUMNS
from hongquant.options.adapters.yfinance_options import fetch_chain_snapshot


class _FakeOptionChain:
    def __init__(self) -> None:
        self.calls = pd.DataFrame(
            [
                {
                    "strike": 500.0,
                    "bid": 2.0,
                    "ask": 2.2,
                    "lastPrice": 2.1,
                    "volume": 100,
                    "openInterest": 1000,
                    "impliedVolatility": 0.22,
                }
            ]
        )
        self.puts = pd.DataFrame(
            [
                {
                    "strike": 500.0,
                    "bid": 1.8,
                    "ask": 2.0,
                    "lastPrice": 1.9,
                    "volume": 80,
                    "openInterest": 900,
                    "impliedVolatility": 0.24,
                }
            ]
        )


class _FakeTicker:
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.options = ["2026-05-15", "2026-05-22"]

    def history(self, *args, **kwargs) -> pd.DataFrame:
        return pd.DataFrame({"Close": [498.0, 501.0]})

    def option_chain(self, expiration: str) -> _FakeOptionChain:
        return _FakeOptionChain()


def test_yfinance_adapter_normalizes_chain(monkeypatch):
    fake_yf = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    df = fetch_chain_snapshot("SPY", expirations=[date(2026, 5, 15)])

    assert list(df.columns) == CHAIN_COLUMNS
    assert len(df) == 2
    assert set(df["option_type"]) == {"call", "put"}
    assert set(df["underlier"]) == {"SPY"}
    assert df["expiration"].tolist() == [date(2026, 5, 15), date(2026, 5, 15)]
    assert df["spot"].iloc[0] == 501.0
    assert df["open_interest"].sum() == 1900
    assert df["gamma"].notna().all()
    assert df["delta"].between(-1, 1).all()


def test_yfinance_adapter_empty_when_requested_expiry_unavailable(monkeypatch):
    fake_yf = types.SimpleNamespace(Ticker=_FakeTicker)
    monkeypatch.setitem(sys.modules, "yfinance", fake_yf)

    df = fetch_chain_snapshot("SPY", expirations=[date(2026, 6, 19)])

    assert df.empty
    assert list(df.columns) == CHAIN_COLUMNS
