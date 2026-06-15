"""CME FedWatch adapter — STUB (pass 2).

Spec §3.1 marks FedWatch scraping as low-stability and *requires* a degradation
proxy. Until the scraper lands, the implied-12m-path component uses the
``DGS2 - EFFR`` proxy (built in series.py as a derived expression), so this stub
just returns empty for the real implied path.
"""
from __future__ import annotations

import pandas as pd

from ..quality import log_parse_failure


def fetch_implied_path_12m() -> pd.Series:
    """Real FedWatch-implied 12m policy path — empty until pass 2 (proxy used instead)."""
    log_parse_failure("fedwatch", "not implemented — using DGS2-EFFR proxy for implied path")
    return pd.Series(dtype="float64")
