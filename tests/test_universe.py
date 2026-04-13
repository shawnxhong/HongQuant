from __future__ import annotations

from hongquant.universe import load_universe


def test_load_universe():
    u = load_universe("configs/universe.yaml")
    assert "SPY" in u.us_broad_etfs
    assert "BTC/USDT" in u.crypto_spot
    assert "DGS10" in u.fred_series
    assert "SPY" in u.all_us_tickers
    assert "BTC/USDT" not in u.all_us_tickers
