"""Daily US equities / ETF OHLCV ingestion.

Pulls from Alpaca (primary) or yfinance (fallback/backfill), normalizes, and
writes to the Parquet lake. Intended to run each trading day after 16:30 ET.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pandas as pd
from prefect import flow, task

from ..data import store
from ..data.adapters import alpaca, yfinance_
from ..data.schema import AssetType, Market
from ..logging import logger, setup_logging
from ..notify import notify

DEFAULT_LOOKBACK_DAYS = 5 * 365


@task(retries=2, retry_delay_seconds=30)
def fetch_symbol(
    symbol: str,
    *,
    interval: str,
    lookback_days: int,
    source: str,
) -> pd.DataFrame:
    setup_logging()
    last_ts = store.latest_timestamp(symbol, interval=interval, market=Market.US.value)
    if last_ts is not None:
        start = (last_ts + timedelta(days=1)).to_pydatetime()
    else:
        start = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    if source == "alpaca":
        df = alpaca.fetch_ohlcv(
            [symbol],
            start=start,
            interval=interval,
            asset_type=AssetType.EQUITY,
        )
    elif source == "yfinance":
        df = yfinance_.fetch_ohlcv(
            [symbol],
            start=start.date().isoformat(),
            interval=interval,
            asset_type=AssetType.EQUITY,
        )
    else:
        raise ValueError(f"Unknown source: {source}")

    logger.info("{}: fetched {} rows from {} since {}", symbol, len(df), source, start)
    return df


@task
def persist(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    paths = store.write_ohlcv(df)
    return len(paths)


@flow(name="daily_equities")
def daily_equities(
    symbols: Iterable[str],
    *,
    interval: str = "1d",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    source: str = "alpaca",
) -> int:
    setup_logging()
    total_rows = 0
    failures: list[str] = []
    for sym in symbols:
        try:
            df = fetch_symbol(sym, interval=interval, lookback_days=lookback_days, source=source)
            persist(df)
            total_rows += len(df)
        except Exception as exc:
            logger.exception("{} failed: {}", sym, exc)
            failures.append(f"{sym}: {exc}")
    if failures:
        notify("⚠️ *daily_equities* failures:\n" + "\n".join(failures))
    logger.info("daily_equities done: {} rows across {} symbols", total_rows, len(list(symbols)))
    return total_rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated tickers")
    p.add_argument("--interval", default="1d")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--source", default="alpaca", choices=["alpaca", "yfinance"])
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    daily_equities(
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        interval=args.interval,
        lookback_days=args.lookback_days,
        source=args.source,
    )
