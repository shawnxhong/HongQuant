"""DuckDB + Parquet data lake.

Layout:

    {parquet_root}/ohlcv/
        market=us/asset_type=equity/interval=1d/year=2025/SPY.parquet
        market=crypto/asset_type=crypto_spot/interval=1h/year=2025/BTCUSDT.parquet

DuckDB is used as the query engine over the Parquet lake; a persistent DuckDB
catalog keeps view definitions for convenience.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import get_settings
from .schema import OHLCV_ARROW_SCHEMA, validate_ohlcv


def _partition_path(
    root: Path, *, market: str, asset_type: str, interval: str, year: int, symbol: str
) -> Path:
    safe_symbol = symbol.replace("/", "_").replace(":", "_")
    return (
        root
        / "ohlcv"
        / f"market={market}"
        / f"asset_type={asset_type}"
        / f"interval={interval}"
        / f"year={year}"
        / f"{safe_symbol}.parquet"
    )


def write_ohlcv(df: pd.DataFrame, *, root: Path | None = None) -> list[Path]:
    """Write a normalized OHLCV DataFrame to the Parquet lake.

    Splits on (symbol, year) so future incremental writes only touch the
    current year's file. Returns the list of written file paths.
    """
    validate_ohlcv(df)
    root = root or get_settings().parquet_root
    root.mkdir(parents=True, exist_ok=True)

    written: list[Path] = []
    df = df.assign(year=df["ts"].dt.year)
    for (symbol, year), chunk in df.groupby(["symbol", "year"], sort=False):
        market = chunk["market"].iat[0]
        asset_type = chunk["asset_type"].iat[0]
        interval = chunk["interval"].iat[0]
        path = _partition_path(
            root,
            market=market,
            asset_type=asset_type,
            interval=interval,
            year=int(year),
            symbol=symbol,
        )
        path.parent.mkdir(parents=True, exist_ok=True)

        new_rows = chunk.drop(columns="year")
        if path.exists():
            # Use ParquetFile to avoid hive-partition column injection from the path.
            existing = pq.ParquetFile(path).read().to_pandas()
            for col in ("symbol", "market", "asset_type", "interval", "source"):
                existing[col] = existing[col].astype(str)
            combined = pd.concat([existing, new_rows], ignore_index=True)
            combined = combined.drop_duplicates(subset=["symbol", "ts"], keep="last")
            combined = combined.sort_values("ts").reset_index(drop=True)
        else:
            combined = new_rows.reset_index(drop=True)

        table = pa.Table.from_pandas(combined, schema=OHLCV_ARROW_SCHEMA, preserve_index=False)
        pq.write_table(table, path, compression="zstd")
        written.append(path)
    return written


def _connect(db_path: Path | None = None) -> duckdb.DuckDBPyConnection:
    path = db_path or get_settings().duckdb_path
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


def register_views(con: duckdb.DuckDBPyConnection, *, root: Path | None = None) -> None:
    """(Re)create the `ohlcv` view over the Parquet lake.

    Uses Hive-style partitioning so `market/asset_type/interval/year` become columns.
    """
    root = root or get_settings().parquet_root
    glob = str(root / "ohlcv" / "**" / "*.parquet")
    con.execute(
        f"""
        CREATE OR REPLACE VIEW ohlcv AS
        SELECT * FROM read_parquet('{glob}', hive_partitioning=TRUE)
        """
    )


def query_ohlcv(
    symbols: Iterable[str] | None = None,
    *,
    interval: str | None = None,
    market: str | None = None,
    start: str | pd.Timestamp | None = None,
    end: str | pd.Timestamp | None = None,
    db_path: Path | None = None,
    root: Path | None = None,
) -> pd.DataFrame:
    con = _connect(db_path)
    register_views(con, root=root)

    where: list[str] = []
    params: list[object] = []
    if symbols is not None:
        symbols_list = list(symbols)
        if symbols_list:
            placeholders = ", ".join(["?"] * len(symbols_list))
            where.append(f"symbol IN ({placeholders})")
            params.extend(symbols_list)
    if interval:
        where.append("interval = ?")
        params.append(interval)
    if market:
        where.append("market = ?")
        params.append(market)
    if start is not None:
        where.append("ts >= ?")
        params.append(pd.Timestamp(start, tz="UTC"))
    if end is not None:
        where.append("ts <= ?")
        params.append(pd.Timestamp(end, tz="UTC"))

    sql = "SELECT symbol, ts, open, high, low, close, volume, market, asset_type, interval, source FROM ohlcv"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY symbol, ts"
    return con.execute(sql, params).df()


def latest_timestamp(
    symbol: str,
    *,
    interval: str,
    market: str,
    db_path: Path | None = None,
    root: Path | None = None,
) -> pd.Timestamp | None:
    """Return the last stored ts for (symbol, interval, market), or None."""
    con = _connect(db_path)
    register_views(con, root=root)
    res = con.execute(
        "SELECT MAX(ts) FROM ohlcv WHERE symbol = ? AND interval = ? AND market = ?",
        [symbol, interval, market],
    ).fetchone()
    if not res or res[0] is None:
        return None
    ts = pd.Timestamp(res[0])
    return ts.tz_convert("UTC") if ts.tzinfo is not None else ts.tz_localize("UTC")
