"""Fragility score store — Parquet, mirrors hongquant/options/store.py conventions.

One file per run date holding every instrument's score. This is also the seed of
the live-calibration ledger (design §7): the ``realized_fwd_return`` column is
written NaN today and back-filled later with the actual forward outcome, so the
system can compute its own running precision per band over time.
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
from .types import FragilityScore

SCORE_SCHEMA = pa.schema(
    [
        ("asof", pa.date32()),
        ("symbol", pa.string()),
        ("cluster", pa.string()),
        ("score", pa.int64()),
        ("band", pa.string()),
        ("pillar_a", pa.float64()),
        ("pillar_b", pa.float64()),
        ("pillar_c", pa.float64()),
        ("systemic_mult", pa.float64()),
        ("confidence", pa.float64()),
        ("rank", pa.int64()),
        ("delta_1d", pa.float64()),
        ("delta_3d", pa.float64()),
        ("realized_fwd_return", pa.float64()),  # ledger seed — back-filled later
    ]
)


def _scores_root(root: Path | None) -> Path:
    return (root or get_settings().parquet_root) / "fragility" / "scores"


def _to_row(s: FragilityScore) -> dict:
    return {
        "asof": s.asof,
        "symbol": s.symbol,
        "cluster": s.cluster or "",
        "score": int(s.score),
        "band": s.band,
        "pillar_a": s.pillar_a,
        "pillar_b": s.pillar_b,
        "pillar_c": s.pillar_c,
        "systemic_mult": s.systemic_mult,
        "confidence": s.confidence,
        "rank": int(s.rank) if s.rank is not None else -1,
        "delta_1d": s.delta_1d,
        "delta_3d": s.delta_3d,
        "realized_fwd_return": float("nan"),
    }


def write_scores(
    scores: list[FragilityScore], *, asof: date, root: Path | None = None
) -> Path | None:
    """Write all of a run's scores to ``fragility/scores/asof=YYYY-MM-DD/scores.parquet``."""
    if not scores:
        return None
    df = pd.DataFrame([_to_row(s) for s in scores])
    df["asof"] = pd.to_datetime(df["asof"]).dt.date
    for col in ("pillar_a", "pillar_b", "pillar_c", "delta_1d", "delta_3d"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("float64")

    path = _scores_root(root) / f"asof={asof.isoformat()}" / "scores.parquet"
    path.parent.mkdir(parents=True, exist_ok=True)
    table = pa.Table.from_pandas(df[[f.name for f in SCORE_SCHEMA]], schema=SCORE_SCHEMA,
                                 preserve_index=False)
    pq.write_table(table, path, compression="zstd")
    logger.info("fragility scores written: {}", path)
    return path


def _query(root: Path | None, where: str, params: list) -> pd.DataFrame:
    glob = str(_scores_root(root) / "asof=*" / "scores.parquet")
    try:
        con = duckdb.connect(":memory:")
        # "asof" is quoted — it collides with DuckDB's reserved ASOF (join) keyword.
        return con.execute(
            f'SELECT * FROM read_parquet(\'{glob}\') WHERE {where} ORDER BY "asof"', params
        ).df()
    except Exception:
        return pd.DataFrame()


def read_history(
    symbol: str, *, before: date | None = None, lookback: int = 400, root: Path | None = None
) -> pd.Series:
    """Return a date-indexed Series of prior scores for ``symbol`` (excludes ``before``)."""
    df = _query(root, "symbol = ?", [symbol])
    if df.empty:
        return pd.Series(dtype=float)
    df["asof"] = pd.to_datetime(df["asof"]).dt.date
    if before is not None:
        df = df[df["asof"] < before]
    if df.empty:
        return pd.Series(dtype=float)
    return df.set_index("asof")["score"].astype(float).sort_index().tail(lookback)


def prior_bands(before: date, *, root: Path | None = None) -> dict[str, str]:
    """Map symbol → band from the most recent run strictly before ``before``."""
    df = _query(root, '"asof" < ?', [before])
    if df.empty:
        return {}
    df["asof"] = pd.to_datetime(df["asof"]).dt.date
    last = df["asof"].max()
    recent = df[df["asof"] == last]
    return dict(zip(recent["symbol"], recent["band"], strict=False))
