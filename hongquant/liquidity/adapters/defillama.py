"""DefiLlama adapter — total stablecoin market cap (global risk-appetite sentinel).

Free, no key (spec §8). The total circulating USD-pegged stablecoin supply moves
faster than equities into risk-off, so it feeds the R composite and alert #10.
Degrades to an empty Series on any failure.
"""
from __future__ import annotations

import httpx
import pandas as pd

from ..quality import log_parse_failure

_URL = "https://stablecoins.llama.fi/stablecoincharts/all"


def fetch_stablecoin_mcap(*, days: int = 800) -> pd.Series:
    """Total USD-pegged stablecoin market cap by day (USD), date-indexed; empty on failure."""
    try:
        resp = httpx.get(_URL, timeout=30.0)
        resp.raise_for_status()
        data = resp.json()
    except Exception as exc:
        log_parse_failure("defillama", f"stablecoin fetch failed: {exc}")
        return pd.Series(dtype="float64")
    if not isinstance(data, list) or not data:
        return pd.Series(dtype="float64")

    rows: dict = {}
    for d in data:
        ts = d.get("date")
        total = d.get("totalCirculatingUSD") or d.get("totalCirculating")
        value = total.get("peggedUSD") if isinstance(total, dict) else total
        if ts is None or value is None:
            continue
        rows[pd.to_datetime(int(ts), unit="s").date()] = float(value)
    if not rows:
        log_parse_failure("defillama", "response had no parseable totalCirculatingUSD rows")
        return pd.Series(dtype="float64")
    return pd.Series(rows).sort_index().tail(days)
