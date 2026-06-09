"""Pillar B — Crowding & Leverage / fuel (design §2 Pillar B).

How many are leaning the same way, with leverage. The hardest pillar to measure
directly, so it is assembled from proxies:

  * COT managed-money net-long percentile — the cleanest crowding read, gold only.
  * IV-RV spread (VRP) — compressed/negative variance premium = cheap insurance
    = complacency.
  * Call-share of OI — call-heavy positioning = chasing / greedy crowding.
  * Gamma-flip proximity — how small a drop flips dealers into amplifying mode.

Dealer-gamma *sign* (the reflexivity engine) is scored in Pillar C, not here, so
the two pillars don't double-count GEX. Instruments without listed options or
COT degrade gracefully — the pillar renormalizes over whatever is available.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from ..options import metrics as m
from .normalize import pct_rank, scale_unit, weighted_mean
from .types import InstrumentFeatures, PillarScore

_WEIGHTS = {
    "cot_mm_net": 0.40,
    "vrp": 0.25,
    "call_share": 0.20,
    "gamma_flip_prox": 0.15,
}


def _front_expiry(feat: InstrumentFeatures) -> date | None:
    if feat.front_expiry is not None:
        return feat.front_expiry
    if feat.chain is not None and not feat.chain.empty and "expiration" in feat.chain:
        exps = pd.to_datetime(feat.chain["expiration"]).dt.date
        return min(exps) if len(exps) else None
    return None


def gamma_flip_strike(gex_df: pd.DataFrame) -> float | None:
    """Strike where cumulative net GEX (low→high) crosses zero — the flip point."""
    if gex_df is None or gex_df.empty or "net_gex" not in gex_df:
        return None
    d = gex_df.sort_values("strike").reset_index(drop=True)
    cum = d["net_gex"].cumsum().to_numpy()
    strikes = d["strike"].to_numpy()
    sign = np.sign(cum)
    crossings = np.where(np.diff(sign) != 0)[0]
    if crossings.size == 0:
        return None
    i = int(crossings[0])
    c0, c1 = cum[i], cum[i + 1]
    s0, s1 = strikes[i], strikes[i + 1]
    if c1 == c0:
        return float(s0)
    return float(s0 + (s1 - s0) * (-c0) / (c1 - c0))  # linear interpolation to zero


def _realized_vol(closes: pd.Series, window: int = 20) -> float:
    rets = closes.pct_change().dropna().tail(window)
    if len(rets) < window // 2:
        return float("nan")
    return float(rets.std() * np.sqrt(252))


def compute(feat: InstrumentFeatures) -> PillarScore:
    """Compute the Crowding pillar (0-1)."""
    parts: dict[str, float | None] = {}
    reasons: list[str] = []

    # --- Gold: COT managed-money net-long percentile (the cleanest crowding read)
    if feat.cot_net is not None and len(feat.cot_net.dropna()) >= 26:
        cot_pctile = pct_rank(feat.cot_net, window=156, min_periods=26)  # ~3y weekly
        parts["cot_mm_net"] = cot_pctile
        if not np.isnan(cot_pctile) and cot_pctile > 0.85:
            reasons.append(f"COT managed-money net long at {cot_pctile:.0%} of 3y range")

    chain = feat.chain
    spot = feat.spot
    expiry = _front_expiry(feat)

    if chain is not None and not chain.empty and spot and expiry is not None:
        # IV-RV variance premium: compressed / negative = cheap insurance = complacency
        iv = m.atm_iv(chain, expiry, spot)
        rv = _realized_vol(feat.closes) if feat.closes is not None else float("nan")
        if not np.isnan(iv) and not np.isnan(rv):
            vrp = iv - rv
            parts["vrp"] = 1.0 - scale_unit(vrp, -0.02, 0.08)  # low/neg VRP -> high crowding
            if vrp < 0.0:
                reasons.append(f"IV-RV spread {vrp:+.0%} — insurance abnormally cheap")

        # Call-share of OI: call-heavy = chasing / greedy
        oi = m.total_oi(chain, expiry)
        total = oi["call"] + oi["put"]
        if total > 0:
            call_share = oi["call"] / total
            parts["call_share"] = scale_unit(call_share, 0.50, 0.75)
            if call_share > 0.68:
                reasons.append(f"call OI {call_share:.0%} of total — upside crowding")

        # Gamma-flip proximity: how small a move flips dealers into amplifying mode
        gex = m.gamma_exposure_by_strike(chain, expiry, spot)
        flip = gamma_flip_strike(gex)
        if flip is not None and spot > 0:
            dist = abs(spot - flip) / spot
            parts["gamma_flip_prox"] = 1.0 - scale_unit(dist, 0.0, 0.06)
            if dist < 0.02:
                reasons.append(f"gamma flip {dist:.1%} from spot — close to amplifying regime")

    if not parts:
        return PillarScore(value=None, reasons=["Pillar B: no options/COT data available"])

    value = weighted_mean(parts, _WEIGHTS)
    clean = {k: v for k, v in parts.items() if v is not None and not np.isnan(v)}
    return PillarScore(value=value, features=clean, reasons=reasons)
