"""Treasury FiscalData adapter — daily TGA (Treasury General Account) balance.

Free, no key (spec §8). Used for the daily plumbing panel; the NetLiq composite
itself uses the weekly FRED ``WTREGEN`` for frequency alignment with WALCL.
Degrades to an empty Series on any failure (the report flags it).
"""
from __future__ import annotations

import httpx
import pandas as pd

from ..quality import log_parse_failure

_URL = (
    "https://api.fiscaldata.treasury.gov/services/api/fiscal_service"
    "/v1/accounting/dts/operating_cash_balance"
)


def fetch_tga_daily(*, days: int = 400) -> pd.Series:
    """Daily TGA closing balance (USD millions), date-indexed; empty on failure."""
    params = {
        "fields": "record_date,account_type,close_today_bal",
        "sort": "-record_date",
        "page[size]": str(days * 3),  # several account_type rows per day
    }
    try:
        resp = httpx.get(_URL, params=params, timeout=20.0)
        resp.raise_for_status()
        data = resp.json().get("data", [])
    except Exception as exc:
        log_parse_failure("treasury", f"TGA fetch failed: {exc}")
        return pd.Series(dtype="float64")
    if not data:
        return pd.Series(dtype="float64")

    df = pd.DataFrame(data)
    mask = df["account_type"].str.contains("TGA|Treasury General", case=False, na=False)
    df = df[mask]
    if df.empty:
        return pd.Series(dtype="float64")
    df["record_date"] = pd.to_datetime(df["record_date"]).dt.date
    df["value"] = pd.to_numeric(df["close_today_bal"], errors="coerce")
    s = df.dropna(subset=["value"]).set_index("record_date")["value"].sort_index()
    return s[~s.index.duplicated(keep="last")].tail(days)
