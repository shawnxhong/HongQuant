"""Shared dataclasses and band logic for the fragility radar."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

import pandas as pd

Band = Literal["Normal", "Watch", "Alert", "Critical"]

# Score-band cut points (design §6). Each band maps to a position/hedge posture.
#   0-40  Normal   (正常)  — maintain
#   40-60 Watch    (关注)  — tighten stops, pause adds
#   60-75 Alert    (警戒)  — trim X% or buy cheap OTM protection
#   75+   Critical (高危)  — cut to core + hedge
BAND_CUTS: list[tuple[float, Band]] = [
    (40.0, "Normal"),
    (60.0, "Watch"),
    (75.0, "Alert"),
]
BAND_LABELS_CN: dict[Band, str] = {
    "Normal": "正常",
    "Watch": "关注",
    "Alert": "警戒",
    "Critical": "高危",
}
BAND_ORDER: dict[Band, int] = {"Normal": 0, "Watch": 1, "Alert": 2, "Critical": 3}


def band_of(score: float) -> Band:
    """Map a 0-100 fragility score to its band."""
    for cut, name in BAND_CUTS:
        if score < cut:
            return name
    return "Critical"


@dataclass
class InstrumentFeatures:
    """Point-in-time raw inputs for one instrument on one as-of date.

    Populated by the flow and consumed by the pillar modules. Anything the data
    feed could not provide is left ``None`` so pillars degrade gracefully.
    """

    symbol: str
    asof: date
    cluster: str | None = None
    closes: pd.Series | None = None          # daily closes, date-indexed (point-in-time)
    spot: float | None = None
    chain: pd.DataFrame | None = None         # options chain snapshot, or None
    front_expiry: date | None = None
    cot_net: pd.Series | None = None          # COT managed-money net history (gold only)
    cot_asof: date | None = None              # true COT release date (T+3 lag honesty)
    cluster_corr: float | None = None         # current within-cluster mean correlation
    cluster_corr_pctile: float | None = None  # its percentile vs the cluster's own history


@dataclass
class PillarScore:
    """One pillar's 0-1 sub-score plus its feature breakdown and reasons."""

    value: float | None                       # 0-1, None if no inputs were available
    features: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


@dataclass
class SystemicGate:
    """Market-level multiplier applied to every instrument's pillar core."""

    multiplier: float                         # bounded, e.g. [0.8, 1.3]
    nfci: float | None = None
    stlfsi: float | None = None
    vix_term: float | None = None             # VIX / VIX3M ratio (>1 = backwardation)
    reasons: list[str] = field(default_factory=list)


@dataclass
class FragilityScore:
    """The full per-instrument radar output for one as-of date."""

    symbol: str
    asof: date
    score: int                                # 0-100
    band: Band
    cluster: str | None = None
    pillar_a: float | None = None
    pillar_b: float | None = None
    pillar_c: float | None = None
    systemic_mult: float = 1.0
    confidence: float = 1.0                   # fraction of pillars that were computable
    rank: int | None = None                   # cross-sectional rank (1 = most fragile)
    delta_1d: float | None = None
    delta_3d: float | None = None
    reasons: list[str] = field(default_factory=list)
    features: dict[str, float] = field(default_factory=dict)
