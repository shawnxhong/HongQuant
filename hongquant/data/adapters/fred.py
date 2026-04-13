"""FRED macro adapter (rates, CPI, VIX, ...)."""
from __future__ import annotations

from typing import Iterable

import pandas as pd

from ...config import get_settings


def fetch_series(series_ids: Iterable[str]) -> pd.DataFrame:
    """Fetch one or more FRED series as a long DataFrame.

    Columns: series_id, ts (UTC), value.
    """
    from fredapi import Fred

    settings = get_settings()
    if not settings.fred_api_key:
        raise RuntimeError("FRED_API_KEY not set")
    fred = Fred(api_key=settings.fred_api_key)

    frames: list[pd.DataFrame] = []
    for sid in series_ids:
        s = fred.get_series(sid)
        if s is None or s.empty:
            continue
        df = s.rename("value").reset_index().rename(columns={"index": "ts"})
        df["ts"] = pd.to_datetime(df["ts"], utc=True)
        df["series_id"] = sid
        frames.append(df[["series_id", "ts", "value"]])
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()
