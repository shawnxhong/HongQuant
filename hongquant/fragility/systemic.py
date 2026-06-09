"""Market-level systemic gate (design §2 "系统性闸门").

Even when watching single names, the whole-market regime modulates everyone's
baseline fragility: when broad financial conditions are tight, every instrument
is more prone to a forced-deleveraging cascade. We read off-the-shelf "finished"
risk gauges — the Chicago Fed NFCI and the St. Louis Fed Financial Stress Index
(STLFSI4) — plus the VIX term structure as a fallback, and turn them into a
single multiplier in [0.8, 1.3] applied to every instrument's pillar core.

These are market risk *measurements*, not bond instruments to trade — no
conflict with the "no bonds" universe constraint (design §2 note).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..data.adapters import fred
from ..logging import logger
from .fragility_pillar import vix_term_score
from .normalize import scale_unit, weighted_mean
from .types import SystemicGate

NFCI_SERIES = "NFCI"        # Chicago Fed National Financial Conditions Index (weekly)
STLFSI_SERIES = "STLFSI4"   # St. Louis Fed Financial Stress Index (weekly)

_STRESS_WEIGHTS = {"nfci": 0.45, "stlfsi": 0.35, "vix_term": 0.20}
_MULT_FLOOR, _MULT_CEIL = 0.80, 1.30


def gate_from_values(
    *,
    nfci: float | None = None,
    stlfsi: float | None = None,
    vix_term: float | None = None,
) -> SystemicGate:
    """Pure mapping of systemic inputs to a bounded multiplier (testable)."""
    parts = {
        "nfci": scale_unit(nfci, -0.6, 1.0) if nfci is not None else None,
        "stlfsi": scale_unit(stlfsi, -1.0, 2.5) if stlfsi is not None else None,
        "vix_term": vix_term,
    }
    stress = weighted_mean(parts, _STRESS_WEIGHTS)
    mult = 1.0 if stress is None else float(np.clip(0.85 + 0.45 * stress, _MULT_FLOOR, _MULT_CEIL))

    reasons: list[str] = []
    if nfci is not None and nfci > 0:
        reasons.append(f"NFCI {nfci:+.2f} — financial conditions tighter than average")
    if stlfsi is not None and stlfsi > 0.5:
        reasons.append(f"STLFSI {stlfsi:+.2f} — elevated financial stress")
    if (vix_term or 0) > 0.7:
        reasons.append("VIX term structure backwardated")
    return SystemicGate(multiplier=round(mult, 3), nfci=nfci, stlfsi=stlfsi,
                        vix_term=vix_term, reasons=reasons)


def _latest(df: pd.DataFrame, series_id: str) -> float | None:
    if df is None or df.empty:
        return None
    sub = df[df["series_id"] == series_id].dropna(subset=["value"])
    if sub.empty:
        return None
    return float(sub.sort_values("ts")["value"].iloc[-1])


def compute_systemic_gate(
    *,
    vix: float | None = None,
    vix3m: float | None = None,
    vix9d: float | None = None,
) -> SystemicGate:
    """Fetch FRED NFCI/STLFSI4 (graceful if no key) + VIX term structure → gate."""
    nfci = stlfsi = None
    try:
        df = fred.fetch_series([NFCI_SERIES, STLFSI_SERIES])
        nfci = _latest(df, NFCI_SERIES)
        stlfsi = _latest(df, STLFSI_SERIES)
    except Exception as exc:
        logger.warning("Systemic gate: FRED unavailable ({}); using VIX term only", exc)

    return gate_from_values(
        nfci=nfci, stlfsi=stlfsi, vix_term=vix_term_score(vix, vix3m, vix9d)
    )
