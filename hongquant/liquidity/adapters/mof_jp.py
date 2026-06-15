"""Japan MOF adapter — STUB (pass 2).

Spec §3.4 / §6 rule #8: 10Y JGB daily yield CSV from the Japanese Ministry of
Finance, used for the carry-funding interrupt alongside USD/JPY. Until it lands,
alert #8 evaluates the USD/JPY leg only (from FRED ``DEXJPUS``).
"""
from __future__ import annotations

import pandas as pd

from ..quality import log_parse_failure


def fetch_jgb_10y() -> pd.Series:
    """10Y JGB yield (daily) — empty until pass 2."""
    log_parse_failure("mof_jp", "JGB CSV not implemented — alert #8 uses USD/JPY leg only")
    return pd.Series(dtype="float64")
