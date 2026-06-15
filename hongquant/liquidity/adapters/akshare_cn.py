"""AKShare China adapter — STUB (pass 2).

Spec §3.4: TSF credit impulse, M1-M2 scissors, PBoC assets via AKShare (interface
drifts with the upstream site → verify function names + degradation path at
implementation time). Until then the China credit-impulse component drops and
the L composite renormalizes. Adding ``akshare`` to deps is a pass-2 task.
"""
from __future__ import annotations

import pandas as pd

from ..quality import log_parse_failure


def fetch_credit_impulse() -> pd.Series:
    """China credit impulse (TSF 12m-rolling / nominal GDP) — empty until pass 2."""
    log_parse_failure("akshare_cn", "credit-impulse fetch not implemented — component dropped")
    return pd.Series(dtype="float64")


def fetch_m1_m2_gap() -> pd.Series:
    """China M1-M2 scissors gap — empty until pass 2."""
    log_parse_failure("akshare_cn", "M1-M2 fetch not implemented")
    return pd.Series(dtype="float64")
