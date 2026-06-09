"""CFTC Commitments of Traders (COT) adapter.

Managed-money net positioning is the cleanest crowding signal for gold/silver
(design §2 Pillar B). We pull the *disaggregated* futures-only report and read
the "Money Manager" long/short columns.

Lag honesty (design §3): COT is Tuesday's positioning released the following
Friday — a T+3 lag. The returned Series is indexed by the report (Tuesday) date;
callers must treat each value as available only from its Friday release. This
adapter degrades to an empty Series on any failure (missing package, network,
unexpected columns) rather than raising — the radar then drops the COT signal
and renormalizes Pillar B over its remaining inputs.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd

from ...logging import logger

# Substring matched against CFTC "Market_and_Exchange_Names" (case-insensitive).
MARKET_SUBSTRINGS: dict[str, str] = {
    "GOLD": "GOLD - COMMODITY EXCHANGE",
    "SILVER": "SILVER - COMMODITY EXCHANGE",
}

_DATE_COL_CANDIDATES = (
    "Report_Date_as_YYYY-MM-DD",
    "As_of_Date_In_Form_YYYY-MM-DD",
    "Report_Date_as_MM_DD_YYYY",
)
_MARKET_COL = "Market_and_Exchange_Names"


def _fetch_disaggregated(years: int) -> pd.DataFrame:
    """Download the last ``years`` of the disaggregated futures-only report."""
    import cot_reports as cot  # lazy import — optional dependency

    this_year = datetime.now().year
    frames: list[pd.DataFrame] = []
    for yr in range(this_year - years + 1, this_year + 1):
        try:
            # store_txt=False: don't litter CWD with the multi-MB scratch file.
            frames.append(
                cot.cot_year(year=yr, cot_report_type="disaggregated_fut",
                             store_txt=False, verbose=False)
            )
        except Exception as exc:
            logger.warning("COT: failed to fetch {} — {}", yr, exc)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def _position_col(columns: list[str], side: str) -> str | None:
    """Resolve the Money-Manager *positions* column for ``side`` ('Long'/'Short').

    Prefers the exact CFTC name; falls back to a fuzzy match that requires
    'positions' and excludes the change / percentage / number-of-traders
    look-alikes (e.g. ``Traders_M_Money_Long_All``, ``Pct_of_OI_M_Money_Long_All``)
    which would otherwise be matched by a naive substring scan.
    """
    exact = f"M_Money_Positions_{side}_All"
    if exact in columns:
        return exact
    blocked = ("change", "pct", "traders", "spread", "_old", "_other")
    for col in columns:
        low = col.lower()
        if all(n in low for n in ("m_money", "positions", side.lower(), "all")) and not any(
            b in low for b in blocked
        ):
            return col
    return None


def managed_money_net(market: str = "GOLD", *, years: int = 4) -> pd.Series:
    """Weekly Money-Manager net positioning (long minus short) for a COT market.

    ``market`` is a key of :data:`MARKET_SUBSTRINGS` (e.g. ``"GOLD"``, ``"SILVER"``)
    or a raw **prefix** matched against the CFTC market name. The prefix is
    anchored at the start so ``"GOLD - COMMODITY EXCHANGE"`` selects COMEX gold
    only and does *not* also pull in ``"MICRO GOLD - COMMODITY EXCHANGE INC."``.
    Returns a date-indexed Series (report/Tuesday dates), empty on failure.
    """
    prefix = MARKET_SUBSTRINGS.get(market.upper(), market).upper()
    try:
        df = _fetch_disaggregated(years)
    except Exception as exc:
        logger.warning("COT unavailable ({}); dropping signal", exc)
        return pd.Series(dtype=float)

    if df.empty or _MARKET_COL not in df.columns:
        return pd.Series(dtype=float)

    cols = list(df.columns)
    date_col = next((c for c in _DATE_COL_CANDIDATES if c in cols), None)
    long_col = _position_col(cols, "Long")
    short_col = _position_col(cols, "Short")
    if not date_col or not long_col or not short_col:
        logger.warning("COT: managed-money columns not found in report; dropping signal")
        return pd.Series(dtype=float)

    names = df[_MARKET_COL].astype(str).str.strip().str.upper()
    sub = df[names.str.startswith(prefix)].copy()
    if sub.empty:
        logger.warning("COT: no rows match market prefix '{}'", prefix)
        return pd.Series(dtype=float)

    sub["_date"] = pd.to_datetime(sub[date_col], errors="coerce")
    sub["_net"] = pd.to_numeric(sub[long_col], errors="coerce") - pd.to_numeric(
        sub[short_col], errors="coerce"
    )
    sub = sub.dropna(subset=["_date", "_net"]).drop_duplicates(subset=["_date"], keep="last")
    out = sub.set_index("_date")["_net"].sort_index()
    out.index = out.index.date
    return out
