from __future__ import annotations

from enum import StrEnum

import pandas as pd
import pyarrow as pa


class Market(StrEnum):
    US = "us"
    CRYPTO = "crypto"


class AssetType(StrEnum):
    EQUITY = "equity"
    ETF = "etf"
    CRYPTO_SPOT = "crypto_spot"
    CRYPTO_PERP = "crypto_perp"


OHLCV_COLUMNS: tuple[str, ...] = (
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
)

OHLCV_ARROW_SCHEMA: pa.Schema = pa.schema(
    [
        ("symbol", pa.string()),
        ("ts", pa.timestamp("ns", tz="UTC")),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.float64()),
        ("market", pa.string()),
        ("asset_type", pa.string()),
        ("interval", pa.string()),
        ("source", pa.string()),
    ]
)


def normalize_ohlcv(
    df: pd.DataFrame,
    *,
    symbol: str,
    market: Market | str,
    asset_type: AssetType | str,
    interval: str,
    source: str,
) -> pd.DataFrame:
    """Coerce a provider DataFrame into the canonical OHLCV schema.

    Accepted input columns (case-insensitive): open/high/low/close/volume and a
    datetime-like index or a `ts`/`timestamp`/`date` column.
    """
    work = df.copy()
    work.columns = [str(c).lower() for c in work.columns]

    if "ts" not in work.columns:
        for cand in ("timestamp", "date", "datetime", "time"):
            if cand in work.columns:
                work = work.rename(columns={cand: "ts"})
                break
        else:
            if isinstance(work.index, pd.DatetimeIndex):
                work = work.reset_index().rename(columns={work.index.name or "index": "ts"})
            else:
                raise ValueError("No timestamp column or DatetimeIndex found")

    required = {"open", "high", "low", "close", "volume"}
    missing = required - set(work.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {missing}")

    work["ts"] = pd.to_datetime(work["ts"], utc=True)
    work["symbol"] = symbol
    work["market"] = str(market)
    work["asset_type"] = str(asset_type)
    work["interval"] = interval
    work["source"] = source

    for col in ("open", "high", "low", "close", "volume"):
        work[col] = pd.to_numeric(work[col], errors="coerce").astype("float64")

    work = work.dropna(subset=["ts", "close"]).sort_values("ts").reset_index(drop=True)
    return work[list(OHLCV_COLUMNS)]


def validate_ohlcv(df: pd.DataFrame) -> None:
    """Assert the DataFrame matches the canonical OHLCV schema."""
    if list(df.columns) != list(OHLCV_COLUMNS):
        raise ValueError(
            f"Column order mismatch. Expected {OHLCV_COLUMNS}, got {tuple(df.columns)}"
        )
    tz = getattr(df["ts"].dtype, "tz", None)
    if tz is None:
        raise ValueError("ts must be tz-aware datetime64[ns, UTC]")
    if str(tz) != "UTC":
        raise ValueError(f"ts must be in UTC, got {tz}")
    if df["symbol"].isna().any():
        raise ValueError("symbol contains NaN")
    if not df["ts"].is_monotonic_increasing:
        raise ValueError("ts is not monotonic increasing")
