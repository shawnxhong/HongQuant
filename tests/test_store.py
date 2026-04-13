from __future__ import annotations

from pathlib import Path

import pandas as pd

from hongquant.data.schema import AssetType, Market, normalize_ohlcv
from hongquant.data.store import (
    latest_timestamp,
    query_ohlcv,
    write_ohlcv,
)


def _sample_bars(symbol: str, start: str, n: int = 5) -> pd.DataFrame:
    idx = pd.date_range(start, periods=n, freq="D", tz="UTC")
    raw = pd.DataFrame(
        {
            "open": range(n),
            "high": range(1, n + 1),
            "low": range(n),
            "close": range(1, n + 1),
            "volume": [1000 + i for i in range(n)],
        },
        index=idx,
    )
    return normalize_ohlcv(
        raw,
        symbol=symbol,
        market=Market.US,
        asset_type=AssetType.ETF,
        interval="1d",
        source="test",
    )


def test_write_read_roundtrip(tmp_path: Path, monkeypatch):
    from hongquant import config

    monkeypatch.setattr(config, "get_settings", lambda: _FakeSettings(tmp_path))

    df1 = _sample_bars("SPY", "2024-12-28", n=6)  # spans year boundary
    paths = write_ohlcv(df1, root=tmp_path / "parquet")
    assert len(paths) == 2  # 2024 + 2025

    db_path = tmp_path / "hq.duckdb"
    out = query_ohlcv(["SPY"], interval="1d", db_path=db_path, root=tmp_path / "parquet")
    assert len(out) == 6
    assert out["symbol"].unique().tolist() == ["SPY"]

    last = latest_timestamp("SPY", interval="1d", market="us", db_path=db_path, root=tmp_path / "parquet")
    assert last is not None
    assert last == df1["ts"].max()


def test_write_is_idempotent(tmp_path: Path):
    df = _sample_bars("QQQ", "2025-01-06", n=3)
    write_ohlcv(df, root=tmp_path / "parquet")
    write_ohlcv(df, root=tmp_path / "parquet")
    out = query_ohlcv(
        ["QQQ"], interval="1d", db_path=tmp_path / "hq.duckdb", root=tmp_path / "parquet"
    )
    assert len(out) == 3


class _FakeSettings:
    def __init__(self, base: Path):
        self.parquet_root = base / "parquet"
        self.duckdb_path = base / "hq.duckdb"
