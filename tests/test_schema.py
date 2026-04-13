from __future__ import annotations

import pandas as pd
import pytest

from hongquant.data.schema import (
    OHLCV_COLUMNS,
    AssetType,
    Market,
    normalize_ohlcv,
    validate_ohlcv,
)


def _raw_bars() -> pd.DataFrame:
    idx = pd.date_range("2024-01-02", periods=3, freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0, 102.0],
            "High": [101.0, 102.5, 103.0],
            "Low": [99.5, 100.5, 101.5],
            "Close": [100.5, 101.5, 102.5],
            "Volume": [1_000_000, 1_100_000, 1_050_000],
        },
        index=idx,
    )


def test_normalize_from_datetimeindex():
    df = normalize_ohlcv(
        _raw_bars(),
        symbol="SPY",
        market=Market.US,
        asset_type=AssetType.ETF,
        interval="1d",
        source="test",
    )
    assert list(df.columns) == list(OHLCV_COLUMNS)
    assert len(df) == 3
    assert df["symbol"].unique().tolist() == ["SPY"]
    assert df["market"].unique().tolist() == ["us"]
    assert str(df["ts"].dtype.tz) == "UTC"
    validate_ohlcv(df)


def test_normalize_from_ts_column():
    raw = _raw_bars().reset_index().rename(columns={"index": "timestamp"})
    df = normalize_ohlcv(
        raw,
        symbol="AAPL",
        market=Market.US,
        asset_type=AssetType.EQUITY,
        interval="1d",
        source="test",
    )
    assert len(df) == 3
    assert df["ts"].is_monotonic_increasing


def test_normalize_rejects_missing_columns():
    bad = _raw_bars().drop(columns=["Volume"])
    with pytest.raises(ValueError, match="Missing OHLCV columns"):
        normalize_ohlcv(
            bad,
            symbol="SPY",
            market=Market.US,
            asset_type=AssetType.ETF,
            interval="1d",
            source="test",
        )


def test_validate_rejects_naive_ts():
    df = normalize_ohlcv(
        _raw_bars(),
        symbol="SPY",
        market=Market.US,
        asset_type=AssetType.ETF,
        interval="1d",
        source="test",
    )
    df = df.assign(ts=df["ts"].dt.tz_localize(None))
    with pytest.raises(ValueError, match="tz-aware"):
        validate_ohlcv(df)
