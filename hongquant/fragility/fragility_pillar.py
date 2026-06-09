"""Pillar C — Fragility / dealer reflexivity (design §2 Pillar C).

How much mechanical, self-reinforcing sell pressure is waiting below. The
defining engine is dealer *negative* gamma: when dealers are short gamma they
sell into weakness, turning an ordinary down move into a stampede. Combined with
the market vol regime (VIX term structure, VVIX, SKEW) and the instrument's
cluster-correlation cascade risk.

Market vol inputs are the same for every instrument on a given day, so the flow
computes them once via :func:`market_vol_scores` and passes the result in.
Dealer-gamma *sign* lives here (not in Pillar B) to avoid double-counting GEX.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..options import metrics as m
from .normalize import pct_rank, scale_unit, weighted_mean
from .types import InstrumentFeatures, PillarScore

_WEIGHTS = {
    "gamma_regime": 0.35,
    "cluster_corr": 0.25,
    "vix_term": 0.20,
    "vvix": 0.10,
    "skew": 0.10,
}


def _front_expiry(feat: InstrumentFeatures) -> date | None:
    if feat.front_expiry is not None:
        return feat.front_expiry
    if feat.chain is not None and not feat.chain.empty and "expiration" in feat.chain:
        exps = pd.to_datetime(feat.chain["expiration"]).dt.date
        return min(exps) if len(exps) else None
    return None


def gamma_regime_score(chain: pd.DataFrame, expiry: date, spot: float) -> float | None:
    """0-1 dealer-gamma fragility: 1.0 = fully short gamma (amplifying), 0.0 = long.

    Uses net/gross GEX ratio so the result is scale-free across instruments.
    """
    gex = m.gamma_exposure_by_strike(chain, expiry, spot)
    if gex.empty:
        return None
    net = float(gex["net_gex"].sum())
    gross = float(gex["call_gex"].abs().sum() + gex["put_gex"].abs().sum())
    if gross <= 0:
        return None
    ratio = net / gross  # in [-1, 1]; negative => dealers short gamma => amplifying
    return scale_unit(-ratio, -1.0, 1.0)


def vix_term_score(vix: float | None, vix3m: float | None, vix9d: float | None) -> float | None:
    """0-1 backwardation score: contango (calm) -> 0, backwardation (stress) -> 1."""
    parts: list[float] = []
    if vix and vix3m and vix3m > 0:
        parts.append(scale_unit(vix / vix3m, 0.92, 1.08))
    if vix and vix9d and vix > 0:
        parts.append(scale_unit(vix9d / vix, 0.95, 1.15))
    return float(np.mean(parts)) if parts else None


def market_vol_scores(
    *,
    vix: float | None = None,
    vix3m: float | None = None,
    vix9d: float | None = None,
    vvix_series: pd.Series | None = None,
    skew_series: pd.Series | None = None,
) -> dict[str, float | None]:
    """Compute the shared market-vol Pillar-C inputs once for the whole run."""
    def _last_pct(s: pd.Series | None) -> float | None:
        if s is None or len(s.dropna()) < 60:
            return None
        r = pct_rank(s)
        return None if np.isnan(r) else r

    return {
        "vix_term": vix_term_score(vix, vix3m, vix9d),
        "vvix": _last_pct(vvix_series),
        "skew": _last_pct(skew_series),
    }


def compute(feat: InstrumentFeatures, market: dict[str, float | None]) -> PillarScore:
    """Compute the Fragility pillar (0-1)."""
    parts: dict[str, float | None] = {}
    reasons: list[str] = []

    chain = feat.chain
    spot = feat.spot
    expiry = _front_expiry(feat)
    if chain is not None and not chain.empty and spot and expiry is not None:
        gr = gamma_regime_score(chain, expiry, spot)
        parts["gamma_regime"] = gr
        if gr is not None and gr > 0.6:
            reasons.append("dealers net short gamma — down moves get amplified")

    if feat.cluster_corr_pctile is not None:
        parts["cluster_corr"] = feat.cluster_corr_pctile
        if feat.cluster_corr_pctile > 0.85:
            reasons.append(
                f"{feat.cluster or 'cluster'} correlation at {feat.cluster_corr_pctile:.0%} "
                "of own history — cascade risk"
            )

    parts["vix_term"] = market.get("vix_term")
    parts["vvix"] = market.get("vvix")
    parts["skew"] = market.get("skew")
    if (market.get("vix_term") or 0) > 0.7:
        reasons.append("VIX term structure in backwardation — front-end stress")

    value = weighted_mean(parts, _WEIGHTS)
    if value is None:
        return PillarScore(value=None, reasons=["Pillar C: no fragility inputs available"])
    clean = {k: v for k, v in parts.items() if v is not None and not np.isnan(v)}
    return PillarScore(value=value, features=clean, reasons=reasons)
