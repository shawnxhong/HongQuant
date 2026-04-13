"""ccxt adapter — unified crypto OHLCV across exchanges."""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Iterable

import pandas as pd

from ..schema import AssetType, Market, normalize_ohlcv

_TF_TO_TIMEDELTA = {
    "1m": timedelta(minutes=1),
    "5m": timedelta(minutes=5),
    "15m": timedelta(minutes=15),
    "1h": timedelta(hours=1),
    "4h": timedelta(hours=4),
    "1d": timedelta(days=1),
}


def _build_exchange(name: str):
    import ccxt

    cls = getattr(ccxt, name, None)
    if cls is None:
        raise ValueError(f"Unknown ccxt exchange: {name}")
    return cls({"enableRateLimit": True})


def fetch_ohlcv(
    symbols: Iterable[str],
    *,
    start: datetime,
    end: datetime | None = None,
    interval: str = "1h",
    exchange: str = "binance",
    asset_type: AssetType = AssetType.CRYPTO_SPOT,
    page_limit: int = 1000,
) -> pd.DataFrame:
    """Fetch OHLCV bars paginating through ccxt fetch_ohlcv."""
    if interval not in _TF_TO_TIMEDELTA:
        raise ValueError(f"Unsupported ccxt interval: {interval}")

    ex = _build_exchange(exchange)
    ex.load_markets()
    end = end or datetime.now(tz=UTC)
    step = _TF_TO_TIMEDELTA[interval]

    frames: list[pd.DataFrame] = []
    for symbol in symbols:
        since_ms = int(start.timestamp() * 1000)
        end_ms = int(end.timestamp() * 1000)
        rows: list[list[float]] = []
        while since_ms < end_ms:
            batch = ex.fetch_ohlcv(symbol, timeframe=interval, since=since_ms, limit=page_limit)
            if not batch:
                break
            rows.extend(batch)
            last_ts = batch[-1][0]
            next_since = last_ts + int(step.total_seconds() * 1000)
            if next_since <= since_ms:
                break
            since_ms = next_since
            time.sleep(ex.rateLimit / 1000)

        if not rows:
            continue

        df = pd.DataFrame(rows, columns=["ts", "open", "high", "low", "close", "volume"])
        df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
        df = df[df["ts"] <= pd.Timestamp(end, tz="UTC")]
        if df.empty:
            continue
        frames.append(
            normalize_ohlcv(
                df,
                symbol=symbol,
                market=Market.CRYPTO,
                asset_type=asset_type,
                interval=interval,
                source=f"ccxt:{exchange}",
            )
        )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
