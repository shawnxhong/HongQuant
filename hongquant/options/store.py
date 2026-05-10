"""Options snapshot Parquet store. Mirrors hongquant/data/store.py conventions."""
from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from ..config import get_settings
from ..logging import logger

OPTIONS_ARROW_SCHEMA = pa.schema(
    [
        ("underlier", pa.string()),
        ("snapshot_ts", pa.timestamp("ns", tz="UTC")),
        ("expiration", pa.date32()),
        ("strike", pa.float64()),
        ("option_type", pa.string()),
        ("bid", pa.float64()),
        ("ask", pa.float64()),
        ("last", pa.float64()),
        ("volume", pa.int64()),
        ("open_interest", pa.int64()),
        ("implied_volatility", pa.float64()),
        ("delta", pa.float64()),
        ("gamma", pa.float64()),
        ("theta", pa.float64()),
        ("vega", pa.float64()),
        ("spot", pa.float64()),
    ]
)


def _snapshot_path(root: Path, underlier: str, snapshot_ts: datetime) -> Path:
    snap_date = snapshot_ts.astimezone(UTC).strftime("%Y-%m-%d")
    snap_time = snapshot_ts.astimezone(UTC).strftime("%H%M%S")
    return (
        root
        / "options"
        / f"underlier={underlier}"
        / f"snapshot_date={snap_date}"
        / f"snapshot_{snap_time}.parquet"
    )


def write_snapshot(df: pd.DataFrame, *, snapshot_ts: datetime | None = None, root: Path | None = None) -> Path:
    """Write an options chain snapshot to the Parquet lake."""
    if df.empty:
        raise ValueError("Cannot write empty snapshot DataFrame")

    ts = snapshot_ts or datetime.now(tz=UTC)
    root = root or get_settings().parquet_root
    underlier = str(df["underlier"].iloc[0])

    path = _snapshot_path(root, underlier, ts)
    path.parent.mkdir(parents=True, exist_ok=True)

    work = df.copy()
    work["snapshot_ts"] = pd.to_datetime(work["snapshot_ts"], utc=True)
    work["expiration"] = pd.to_datetime(work["expiration"]).dt.date
    for col in ("volume", "open_interest"):
        work[col] = work[col].fillna(0).astype("int64")
    for col in ("bid", "ask", "last", "implied_volatility", "delta", "gamma", "theta", "vega", "spot", "strike"):
        work[col] = pd.to_numeric(work[col], errors="coerce").astype("float64")

    schema_cols = [f.name for f in OPTIONS_ARROW_SCHEMA]
    work = work[[c for c in schema_cols if c in work.columns]]

    table = pa.Table.from_pandas(work, schema=OPTIONS_ARROW_SCHEMA, preserve_index=False)
    pq.write_table(table, path, compression="zstd")
    logger.info("options snapshot written: {}", path)
    return path


def read_snapshot(underlier: str, snapshot_date: date, *, root: Path | None = None) -> pd.DataFrame:
    """Read all snapshots for a given underlier and date (may be multiple intraday)."""
    root = root or get_settings().parquet_root
    date_str = snapshot_date.isoformat()
    glob = str(root / "options" / f"underlier={underlier}" / f"snapshot_date={date_str}" / "*.parquet")
    try:
        con = duckdb.connect(":memory:")
        return con.execute(f"SELECT * FROM read_parquet('{glob}')").df()
    except Exception:
        return pd.DataFrame()


def historical_friday_oi(underlier: str, *, weeks: int = 12, root: Path | None = None) -> pd.Series:
    """Return total OI for each past front-Friday expiry from stored snapshots.

    Used to compute oi_vs_baseline. Index = snapshot_date, values = total OI.
    Returns an empty Series if insufficient data.
    """
    root = root or get_settings().parquet_root
    glob = str(root / "options" / f"underlier={underlier}" / "*" / "*.parquet")
    try:
        con = duckdb.connect(":memory:")
        df = con.execute(
            f"""
            SELECT
                CAST(snapshot_ts AS DATE) AS snap_date,
                expiration,
                SUM(open_interest) AS total_oi
            FROM read_parquet('{glob}')
            WHERE dayofweek(CAST(expiration AS DATE)) = 5   -- Friday
            GROUP BY snap_date, expiration
            ORDER BY snap_date
            """
        ).df()
    except Exception:
        return pd.Series(dtype=float)

    if df.empty:
        return pd.Series(dtype=float)

    # Keep only rows where the expiration was the nearest Friday on that snap_date
    df["snap_date"] = pd.to_datetime(df["snap_date"]).dt.date
    df["expiration"] = pd.to_datetime(df["expiration"]).dt.date
    recent = df.tail(weeks * 5).groupby("snap_date")["total_oi"].sum()
    return recent.tail(weeks)


def historical_atm_iv(underlier: str, *, weeks: int = 52, root: Path | None = None) -> pd.Series:
    """Return the front-week ATM IV per trading day for IV rank computation.

    Index = snapshot_date (date), values = front-week ATM IV (fraction).
    """
    root = root or get_settings().parquet_root
    glob = str(root / "options" / f"underlier={underlier}" / "*" / "*.parquet")
    try:
        con = duckdb.connect(":memory:")
        # Approximate ATM IV: average IV of contracts closest to spot, front expiry
        df = con.execute(
            f"""
            WITH ranked AS (
                SELECT
                    CAST(snapshot_ts AS DATE) AS snap_date,
                    expiration,
                    ABS(strike - spot) AS dist,
                    implied_volatility,
                    ROW_NUMBER() OVER (PARTITION BY CAST(snapshot_ts AS DATE), expiration, option_type
                                       ORDER BY ABS(strike - spot)) AS rn
                FROM read_parquet('{glob}')
                WHERE implied_volatility > 0
            ),
            atm AS (
                SELECT snap_date, expiration, AVG(implied_volatility) AS atm_iv
                FROM ranked WHERE rn = 1
                GROUP BY snap_date, expiration
            ),
            front AS (
                SELECT snap_date, MIN(expiration) AS front_exp
                FROM atm GROUP BY snap_date
            )
            SELECT a.snap_date, a.atm_iv
            FROM atm a JOIN front f ON a.snap_date = f.snap_date AND a.expiration = f.front_exp
            ORDER BY a.snap_date
            """
        ).df()
    except Exception:
        return pd.Series(dtype=float)

    if df.empty:
        return pd.Series(dtype=float)

    df["snap_date"] = pd.to_datetime(df["snap_date"]).dt.date
    return df.set_index("snap_date")["atm_iv"].tail(weeks)
