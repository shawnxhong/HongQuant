"""Alpaca Market Data adapter (US equities/ETFs)."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Iterable

import pandas as pd

from ...config import get_settings
from ..schema import AssetType, Market, normalize_ohlcv


def _client():
    # Lazy import so the package is importable without alpaca-py installed.
    from alpaca.data.historical import StockHistoricalDataClient

    settings = get_settings()
    if not settings.alpaca_api_key or not settings.alpaca_api_secret:
        raise RuntimeError("ALPACA_API_KEY / ALPACA_API_SECRET not set")
    return StockHistoricalDataClient(settings.alpaca_api_key, settings.alpaca_api_secret)


def _timeframe(interval: str):
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    mapping = {
        "1m": TimeFrame(1, TimeFrameUnit.Minute),
        "5m": TimeFrame(5, TimeFrameUnit.Minute),
        "15m": TimeFrame(15, TimeFrameUnit.Minute),
        "1h": TimeFrame(1, TimeFrameUnit.Hour),
        "1d": TimeFrame(1, TimeFrameUnit.Day),
    }
    if interval not in mapping:
        raise ValueError(f"Unsupported interval for Alpaca: {interval}")
    return mapping[interval]


def fetch_ohlcv(
    symbols: Iterable[str],
    *,
    start: datetime,
    end: datetime | None = None,
    interval: str = "1d",
    asset_type: AssetType = AssetType.EQUITY,
) -> pd.DataFrame:
    """Fetch OHLCV bars from Alpaca, returned in canonical schema."""
    from alpaca.data.requests import StockBarsRequest

    end = end or datetime.now(tz=UTC)
    client = _client()
    req = StockBarsRequest(
        symbol_or_symbols=list(symbols),
        timeframe=_timeframe(interval),
        start=start,
        end=end,
        feed="iex",  # free feed; upgrade to "sip" with paid subscription
    )
    bars = client.get_stock_bars(req).df
    if bars is None or bars.empty:
        return pd.DataFrame(
            columns=[
                "symbol",
                "ts",
                "open",
                "high",
                "low",
                "close",
                "volume",
                "market",
                "asset_type",
                "interval",
                "source",
            ]
        )

    bars = bars.reset_index()
    frames: list[pd.DataFrame] = []
    for symbol, group in bars.groupby("symbol", sort=False):
        frames.append(
            normalize_ohlcv(
                group.rename(columns={"timestamp": "ts"}),
                symbol=symbol,
                market=Market.US,
                asset_type=asset_type,
                interval=interval,
                source="alpaca",
            )
        )
    return pd.concat(frames, ignore_index=True)
