"""Gated composition of the three pillars into a 0-100 fragility score (design §4).

Composition is a **gated geometric mean**, not a sum: a flash crash needs
Extension AND Crowding AND Fragility together, so any pillar near zero must
suppress the whole score. Geometric mean enforces that co-occurrence. The result
is then scaled by the market-level systemic multiplier.

Also here: cross-sectional ranking (an instrument that is an extension+crowding
outlier vs the rest of the watchlist is more dangerous than its absolute score
suggests, design §4) and change detection (alerts fire on band crossings and
rapid deterioration, not on absolute level, design §6).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from .types import BAND_ORDER, Band, FragilityScore, PillarScore, SystemicGate, band_of

RAPID_DELTA = 15.0          # a +15 jump over 3 days is "rapidly deteriorating"
_GEO_FLOOR = 1e-3           # keep log() finite when a pillar is ~0


def _geomean(values: list[float]) -> float:
    vals = [min(max(v, _GEO_FLOOR), 1.0) for v in values]
    return float(np.exp(np.mean(np.log(vals))))


def compute_fragility(
    symbol: str,
    asof: date,
    *,
    pillar_a: PillarScore,
    pillar_b: PillarScore,
    pillar_c: PillarScore,
    gate: SystemicGate,
    cluster: str | None = None,
) -> FragilityScore:
    """Combine the three pillars and the systemic gate into a FragilityScore."""
    a, b, c = pillar_a.value, pillar_b.value, pillar_c.value
    available = [v for v in (a, b, c) if v is not None and not np.isnan(v)]
    confidence = len(available) / 3.0

    if not available:
        score = 0
    else:
        core = _geomean(available)
        score = round(float(np.clip(core * gate.multiplier, 0.0, 1.0)) * 100)

    band = band_of(score)

    reasons: list[str] = []
    reasons += pillar_a.reasons + pillar_b.reasons + pillar_c.reasons
    reasons += gate.reasons[:1]
    if confidence < 1.0:
        missing = [n for n, v in (("A", a), ("B", b), ("C", c)) if v is None or np.isnan(v)]
        reasons.append(f"reduced confidence — pillar(s) {','.join(missing)} unavailable")

    features: dict[str, float] = {}
    for prefix, ps in (("a", pillar_a), ("b", pillar_b), ("c", pillar_c)):
        for k, v in ps.features.items():
            features[f"{prefix}_{k}"] = round(float(v), 4)

    return FragilityScore(
        symbol=symbol,
        asof=asof,
        score=score,
        band=band,
        cluster=cluster,
        pillar_a=round(a, 4) if a is not None else None,
        pillar_b=round(b, 4) if b is not None else None,
        pillar_c=round(c, 4) if c is not None else None,
        systemic_mult=gate.multiplier,
        confidence=round(confidence, 3),
        reasons=reasons,
        features=features,
    )


def rank_and_flag(scores: list[FragilityScore]) -> None:
    """Assign cross-sectional rank (1 = most fragile) and flag (A+B) outliers in place."""
    for i, s in enumerate(sorted(scores, key=lambda s: s.score, reverse=True), 1):
        s.rank = i

    ab = [
        s.pillar_a + s.pillar_b
        for s in scores
        if s.pillar_a is not None and s.pillar_b is not None
    ]
    if len(ab) >= 3:
        mean, std = float(np.mean(ab)), float(np.std(ab))
        if std > 0:
            for s in scores:
                if (
                    s.pillar_a is not None
                    and s.pillar_b is not None
                    and ((s.pillar_a + s.pillar_b) - mean) / std > 1.0
                ):
                    s.reasons.append(
                        "extension+crowding outlier vs the rest of the watchlist"
                    )


def attach_deltas(score: FragilityScore, history: pd.Series | None) -> None:
    """Set delta_1d / delta_3d from a date-indexed history of prior scores (excl. today)."""
    if history is None or history.empty:
        return
    hist = history.sort_index()
    score.delta_1d = round(score.score - float(hist.iloc[-1]), 1)
    ref = hist.iloc[-3] if len(hist) >= 3 else hist.iloc[0]
    score.delta_3d = round(score.score - float(ref), 1)


def is_state_change(score: FragilityScore, prev_band: Band | None) -> bool:
    """Should this fire a push alert (vs. appear only in the daily digest)?

    True on first sighting at Watch+, on any upward band crossing, or on rapid
    deterioration (design §6 "only push on state switch").
    """
    new = BAND_ORDER[score.band]
    if prev_band is None:
        return new >= BAND_ORDER["Watch"]
    if new > BAND_ORDER[prev_band]:
        return True
    return score.delta_3d is not None and score.delta_3d >= RAPID_DELTA
