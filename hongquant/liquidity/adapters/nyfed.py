"""NY Fed adapter — STUB (pass 2).

Spec §3.2 / §6 rule #3: Standing Repo Facility (SRF) usage and ACM term premium
from NY Fed public data. Until it lands, the SRF interrupt (#3) and the ACM
context series are skipped.
"""
from __future__ import annotations

import pandas as pd

from ..quality import log_parse_failure


def fetch_srf_usage() -> pd.Series:
    """Standing Repo Facility usage (daily) — empty until pass 2."""
    log_parse_failure("nyfed", "SRF usage not implemented — alert #3 skipped")
    return pd.Series(dtype="float64")


def fetch_acm_term_premium() -> pd.Series:
    """ACM 10Y term premium (daily) — empty until pass 2."""
    log_parse_failure("nyfed", "ACM term premium not implemented")
    return pd.Series(dtype="float64")
