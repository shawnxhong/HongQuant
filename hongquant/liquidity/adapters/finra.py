"""FINRA margin-debt adapter — STUB (pass 2).

Spec §3.3: monthly margin statistics scraped from FINRA's page (~3-4w lag,
page-redesign risk → parse-failure alert required). Until the scraper lands the
R composite drops the margin-debt component and renormalizes.
"""
from __future__ import annotations

import pandas as pd

from ..quality import log_parse_failure


def fetch_margin_debt() -> pd.Series:
    """Monthly FINRA margin debt — empty until pass 2."""
    log_parse_failure("finra", "margin-debt scraper not implemented — component dropped")
    return pd.Series(dtype="float64")
