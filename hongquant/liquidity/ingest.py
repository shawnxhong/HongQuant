"""Fetch the series catalog into the vintage store (one as-of snapshot per run).

Reliable free sources only this pass: FRED (bulk), DefiLlama, yfinance. Each
fetch degrades independently — a failure logs and is skipped, leaving the
composite to drop-and-renormalize. Stub sources in the catalog are not fetched.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd

from ..logging import logger
from . import store
from .adapters.defillama import fetch_stablecoin_mcap
from .config_load import SeriesCatalogEntry


def _yf_close(ticker: str, *, period: str = "5y") -> pd.Series:
    """Daily close for a yfinance ticker as a date-indexed Series (empty on failure)."""
    try:
        import yfinance as yf

        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=True)
    except Exception as exc:
        logger.warning("yfinance fetch failed for {}: {}", ticker, exc)
        return pd.Series(dtype="float64")
    if df is None or df.empty:
        return pd.Series(dtype="float64")
    close = df["Close"]
    if isinstance(close, pd.DataFrame):  # MultiIndex single-ticker frame
        close = close.iloc[:, 0]
    close = close.dropna()
    close.index = pd.to_datetime(close.index).date
    return pd.Series(close.to_numpy(dtype="float64"), index=close.index)


def ingest_catalog(
    catalog: list[SeriesCatalogEntry],
    *,
    as_of: date,
    root: Path | None = None,
) -> dict[str, int]:
    """Pull every enabled catalog series and append it to the vintage store.

    Returns ``{series_id: rows_written}`` for what succeeded.
    """
    freq = {e.id: e.frequency for e in catalog}
    written: dict[str, int] = {}

    def _persist(sid: str, s: pd.Series) -> None:
        if s is None or s.empty:
            logger.warning("LRM ingest: {} returned no data", sid)
            return
        store.write_vintages(sid, s, as_of=as_of, frequency=freq.get(sid, "daily"), root=root)
        written[sid] = len(s)

    # FRED — one bulk call for every enabled FRED id.
    fred_ids = [e.id for e in catalog if e.source == "fred" and e.enabled]
    if fred_ids:
        try:
            from ..data.adapters.fred import fetch_series

            df = fetch_series(fred_ids)
        except Exception as exc:
            logger.warning("FRED bulk fetch failed: {}", exc)
            df = pd.DataFrame()
        for sid in fred_ids:
            sub = df[df["series_id"] == sid] if not df.empty else df
            if sub.empty:
                _persist(sid, pd.Series(dtype="float64"))
                continue
            s = pd.Series(
                pd.to_numeric(sub["value"], errors="coerce").to_numpy(),
                index=pd.to_datetime(sub["ts"]).dt.date,
            ).dropna().sort_index()
            _persist(sid, s)

    # DefiLlama stablecoins.
    for e in catalog:
        if e.source == "defillama" and e.enabled:
            _persist(e.id, fetch_stablecoin_mcap())

    # yfinance closes.
    for e in catalog:
        if e.source == "yfinance" and e.enabled:
            _persist(e.id, _yf_close(e.ticker or e.id))

    logger.info("LRM ingest complete: {}/{} series populated", len(written), len(catalog))
    return written
