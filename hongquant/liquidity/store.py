"""Vintage time-series store — DuckDB + Parquet, one file per series.

The one genuinely new primitive in LRM. Every observation is stored with its
vintage triple ``(observation_date, as_of_date, value)`` plus frequency, so any
read can be made point-in-time: revisions accumulate as new rows rather than
overwriting, and ``read_series_asof`` returns only what was knowable at a given
``as_of`` (spec §1.2, §10 — the anti-future-function guarantee).

Layout: ``parquet_root/liquidity/vintages/series={id}/data.parquet``.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import get_settings
from ..logging import logger

VINTAGE_SCHEMA = pa.schema(
    [
        ("series_id", pa.string()),
        ("observation_date", pa.date32()),
        ("as_of_date", pa.date32()),
        ("value", pa.float64()),
        ("frequency", pa.string()),
    ]
)
_COLS = [f.name for f in VINTAGE_SCHEMA]
_FAR_FUTURE = date(9999, 12, 31)


def _vintages_root(root: Path | None) -> Path:
    return (root or get_settings().parquet_root) / "liquidity" / "vintages"


def _path(series_id: str, root: Path | None) -> Path:
    return _vintages_root(root) / f"series={series_id}" / "data.parquet"


def _normalize(series_id: str, frame: pd.Series | pd.DataFrame, as_of: date, frequency: str) -> pd.DataFrame:
    if isinstance(frame, pd.Series):
        df = frame.rename("value").reset_index()
        df.columns = ["observation_date", "value"]
    else:
        df = frame.rename(columns={frame.columns[0]: "observation_date", frame.columns[1]: "value"}).copy()
    df["observation_date"] = pd.to_datetime(df["observation_date"]).dt.date
    df["value"] = pd.to_numeric(df["value"], errors="coerce").astype("float64")
    df = df.dropna(subset=["value"])
    df["series_id"] = series_id
    df["as_of_date"] = as_of
    df["frequency"] = frequency
    return df[_COLS]


def write_vintages(
    series_id: str,
    frame: pd.Series | pd.DataFrame,
    *,
    as_of: date,
    frequency: str,
    root: Path | None = None,
) -> Path | None:
    """Append a vintage snapshot of ``series_id``.

    ``frame`` is a date-indexed Series (or 2-col DataFrame) of observations as
    known on ``as_of``. Existing rows for other ``as_of`` dates are preserved;
    rewriting the same ``(observation_date, as_of_date)`` overwrites that cell.
    """
    df = _normalize(series_id, frame, as_of, frequency)
    if df.empty:
        logger.warning("liquidity store: {} had no usable rows on {}", series_id, as_of)
        return None
    path = _path(series_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        existing = pq.read_table(path).to_pandas()
        df = pd.concat([existing, df], ignore_index=True)
    df = df.drop_duplicates(subset=["observation_date", "as_of_date"], keep="last")
    table = pa.Table.from_pandas(df[_COLS], schema=VINTAGE_SCHEMA, preserve_index=False)
    pq.write_table(table, path, compression="zstd")
    logger.info("liquidity vintage written: {} ({} rows, as_of {})", series_id, len(df), as_of)
    return path


def read_series_asof(series_id: str, *, as_of: date, root: Path | None = None) -> pd.Series:
    """Point-in-time series: latest value per observation_date with as_of_date ≤ ``as_of``."""
    path = _path(series_id, root)
    if not path.exists():
        return pd.Series(dtype="float64")
    query = """
        SELECT observation_date, value FROM (
            SELECT observation_date, value, as_of_date,
                   row_number() OVER (PARTITION BY observation_date ORDER BY as_of_date DESC) AS rn
            FROM read_parquet(?)
            WHERE as_of_date <= ?
        ) WHERE rn = 1
        ORDER BY observation_date
    """
    try:
        con = duckdb.connect(":memory:")
        df = con.execute(query, [str(path), as_of]).df()
    except Exception as exc:
        logger.warning("liquidity store read failed for {}: {}", series_id, exc)
        return pd.Series(dtype="float64")
    if df.empty:
        return pd.Series(dtype="float64")
    idx = pd.to_datetime(df["observation_date"]).dt.date
    s = pd.Series(df["value"].to_numpy(dtype="float64"), index=idx, name=series_id)
    s.index.name = "observation_date"
    return s


def latest(series_id: str, *, root: Path | None = None) -> pd.Series:
    """Most-recent-vintage view of a series (ignores point-in-time discipline)."""
    return read_series_asof(series_id, as_of=_FAR_FUTURE, root=root)


def staleness_days(series_id: str, *, as_of: date, root: Path | None = None) -> int | None:
    """Days between ``as_of`` and the latest observation knowable then; None if absent."""
    s = read_series_asof(series_id, as_of=as_of, root=root)
    if s.empty:
        return None
    return (as_of - max(s.index)).days
