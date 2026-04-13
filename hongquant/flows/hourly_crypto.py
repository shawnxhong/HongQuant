"""Hourly crypto OHLCV ingestion via ccxt."""
from __future__ import annotations

import argparse
from collections.abc import Iterable
from datetime import UTC, datetime, timedelta

import pandas as pd
from prefect import flow, task

from ..data import store
from ..data.adapters import ccxt_
from ..data.schema import AssetType, Market
from ..logging import logger, setup_logging
from ..notify import notify

DEFAULT_LOOKBACK_DAYS = 365 * 3


@task(retries=2, retry_delay_seconds=30)
def fetch_symbol(
    symbol: str,
    *,
    interval: str,
    lookback_days: int,
    exchange: str,
) -> pd.DataFrame:
    setup_logging()
    last_ts = store.latest_timestamp(symbol, interval=interval, market=Market.CRYPTO.value)
    if last_ts is not None:
        start = (last_ts + timedelta(minutes=1)).to_pydatetime()
    else:
        start = datetime.now(tz=UTC) - timedelta(days=lookback_days)

    df = ccxt_.fetch_ohlcv(
        [symbol],
        start=start,
        interval=interval,
        exchange=exchange,
        asset_type=AssetType.CRYPTO_SPOT,
    )
    logger.info("{} ({}): fetched {} rows since {}", symbol, exchange, len(df), start)
    return df


@task
def persist(df: pd.DataFrame) -> int:
    if df.empty:
        return 0
    paths = store.write_ohlcv(df)
    return len(paths)


@flow(name="hourly_crypto")
def hourly_crypto(
    symbols: Iterable[str],
    *,
    interval: str = "1h",
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    exchange: str = "binance",
) -> int:
    setup_logging()
    total_rows = 0
    failures: list[str] = []
    symbols_list = list(symbols)
    for sym in symbols_list:
        try:
            df = fetch_symbol(sym, interval=interval, lookback_days=lookback_days, exchange=exchange)
            persist(df)
            total_rows += len(df)
        except Exception as exc:
            logger.exception("{} failed: {}", sym, exc)
            failures.append(f"{sym}: {exc}")
    if failures:
        notify("⚠️ *hourly_crypto* failures:\n" + "\n".join(failures))
    logger.info("hourly_crypto done: {} rows across {} symbols", total_rows, len(symbols_list))
    return total_rows


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--symbols", required=True, help="comma-separated ccxt symbols, e.g. BTC/USDT,ETH/USDT")
    p.add_argument("--interval", default="1h")
    p.add_argument("--lookback-days", type=int, default=DEFAULT_LOOKBACK_DAYS)
    p.add_argument("--exchange", default="binance")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    hourly_crypto(
        symbols=[s.strip() for s in args.symbols.split(",") if s.strip()],
        interval=args.interval,
        lookback_days=args.lookback_days,
        exchange=args.exchange,
    )
