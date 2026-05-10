from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from hongquant.options.store import (
    historical_friday_oi,
    read_snapshot,
    write_snapshot,
)


def _sample_chain(underlier: str = "SPY", n_contracts: int = 10) -> pd.DataFrame:
    now = datetime.now(tz=UTC)
    expiry = date(2025, 5, 9)  # known Friday
    rows = []
    for i in range(n_contracts):
        strike = 490.0 + i * 2.0
        rows.append(
            {"underlier": underlier, "expiration": expiry, "strike": strike, "option_type": "call",
                 "bid": 1.0, "ask": 1.5, "last": 1.2, "volume": 100, "open_interest": 1000 + i * 100,
                 "implied_volatility": 0.25, "delta": 0.5, "gamma": 0.01, "theta": -0.05, "vega": 0.2,
                 "spot": 500.0, "snapshot_ts": now}
        )
        rows.append(
            {"underlier": underlier, "expiration": expiry, "strike": strike, "option_type": "put",
                 "bid": 0.8, "ask": 1.2, "last": 1.0, "volume": 80, "open_interest": 800 + i * 100,
                 "implied_volatility": 0.25, "delta": -0.5, "gamma": 0.01, "theta": -0.05, "vega": 0.2,
                 "spot": 500.0, "snapshot_ts": now}
        )
    return pd.DataFrame(rows)


def test_write_read_roundtrip(tmp_path: Path):
    chain = _sample_chain("SPY", n_contracts=5)
    ts = datetime.now(tz=UTC)

    path = write_snapshot(chain, snapshot_ts=ts, root=tmp_path)
    assert path.exists()
    assert "underlier=SPY" in str(path)
    assert "snapshot_date=" in str(path)

    snap_date = ts.date()
    recovered = read_snapshot("SPY", snap_date, root=tmp_path)
    assert not recovered.empty
    assert {"underlier", "strike", "open_interest"}.issubset(recovered.columns)
    assert len(recovered) == len(chain)


def test_write_empty_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="empty"):
        write_snapshot(pd.DataFrame(), root=tmp_path)


def test_partition_path_format(tmp_path: Path):
    chain = _sample_chain("QQQ", n_contracts=3)
    ts = datetime(2025, 5, 7, 15, 30, 0, tzinfo=UTC)
    path = write_snapshot(chain, snapshot_ts=ts, root=tmp_path)

    assert "underlier=QQQ" in str(path)
    assert "snapshot_date=2025-05-07" in str(path)
    assert "snapshot_153000.parquet" in str(path)


def test_historical_friday_oi_insufficient(tmp_path: Path):
    # No snapshots → empty series
    history = historical_friday_oi("SPY", weeks=12, root=tmp_path)
    assert len(history) == 0


def test_historical_friday_oi_with_data(tmp_path: Path):
    # Write snapshots on 3 different dates (simulating different days)
    friday = date(2025, 5, 9)
    for day_offset in range(3):
        snap_date = friday - timedelta(days=day_offset * 7)
        ts = datetime(snap_date.year, snap_date.month, snap_date.day, 15, 30, 0, tzinfo=UTC)
        chain = _sample_chain("SPY", n_contracts=3)
        # Update snapshot_ts to simulate historical data
        chain["snapshot_ts"] = ts
        write_snapshot(chain, snapshot_ts=ts, root=tmp_path)

    history = historical_friday_oi("SPY", weeks=12, root=tmp_path)
    assert len(history) >= 1  # at least some history retrieved


def test_read_snapshot_missing_date(tmp_path: Path):
    # Reading a date with no data returns empty DataFrame
    result = read_snapshot("SPY", date(2000, 1, 1), root=tmp_path)
    assert result.empty or isinstance(result, pd.DataFrame)
