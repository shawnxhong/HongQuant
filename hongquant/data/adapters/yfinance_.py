"""yfinance adapter — free, used as cross-check and backfill."""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

import pandas as pd

from ..schema import AssetType, Market, normalize_ohlcv


def fetch_ohlcv(
    symbols: Iterable[str],
    *,
    start: datetime | str | None = None,
    end: datetime | str | None = None,
    interval: str = "1d",
    asset_type: AssetType = AssetType.EQUITY,
) -> pd.DataFrame:
    import yfinance as yf

    tickers = list(symbols)
    if not tickers:
        return pd.DataFrame()

    # auto_adjust=True -> adjusted OHLC for splits/divs (what we want for backtesting).
    # group_by='ticker' -> consistent per-ticker slicing for 1 or many tickers.
    raw = yf.download(
        tickers=tickers,
        start=start,
        end=end,
        interval=interval,
        auto_adjust=True,
        progress=False,
        threads=True,
        group_by="ticker",
    )
    if raw is None or raw.empty:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []
    if len(tickers) == 1:
        df = raw.copy()
        df.columns = [c.lower() if isinstance(c, str) else c for c in df.columns]
        frames.append(
            normalize_ohlcv(
                df,
                symbol=tickers[0],
                market=Market.US,
                asset_type=asset_type,
                interval=interval,
                source="yfinance",
            )
        )
    else:
        for sym in tickers:
            if sym not in raw.columns.get_level_values(0):
                continue
            sub = raw[sym].copy()
            sub.columns = [str(c).lower() for c in sub.columns]
            if sub["close"].dropna().empty:
                continue
            frames.append(
                normalize_ohlcv(
                    sub,
                    symbol=sym,
                    market=Market.US,
                    asset_type=asset_type,
                    interval=interval,
                    source="yfinance",
                )
            )
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
