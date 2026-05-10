"""0-100 Momentum Crash Risk Score with component breakdown."""
from __future__ import annotations

from datetime import date

import numpy as np

from .types import Event, RiskScore, SnapshotBundle

# ---------------------------------------------------------------------------
# Threshold tables -- edit these to tune signal sensitivity
# ---------------------------------------------------------------------------

# IV term structure: front_iv_premium (fraction, e.g. 0.32 = 32%)
_IV_PREMIUM_THRESHOLDS = [
    (0.00, 0.00),
    (0.10, 0.20),
    (0.20, 0.50),
    (0.35, 0.85),
    (0.50, 1.00),
]

# OI vs 12-week baseline (ratio, e.g. 1.8 = 1.8x normal)
_OI_BASELINE_THRESHOLDS = [
    (1.0, 0.00),
    (1.3, 0.20),
    (1.5, 0.40),
    (1.8, 0.70),
    (2.0, 1.00),
]

# Volume/OI ratio (intraday activity)
_VOL_OI_THRESHOLDS = [
    (0.05, 0.00),
    (0.20, 0.20),
    (0.40, 0.50),
    (0.60, 0.75),
    (0.80, 1.00),
]

# VIX level
_VIX_LEVEL_THRESHOLDS = [
    (15.0, 0.00),
    (18.0, 0.20),
    (22.0, 0.50),
    (27.0, 0.75),
    (33.0, 1.00),
]

# IV rank (0-100)
_IV_RANK_THRESHOLDS = [
    (30.0, 0.00),
    (50.0, 0.30),
    (70.0, 0.60),
    (80.0, 0.80),
    (90.0, 1.00),
]


def _interp(value: float, thresholds: list[tuple[float, float]]) -> float:
    """Linear interpolation over a piecewise threshold table."""
    if np.isnan(value):
        return 0.0
    xs = [t[0] for t in thresholds]
    ys = [t[1] for t in thresholds]
    return float(np.clip(np.interp(value, xs, ys), 0.0, 1.0))


# Component weights (must sum to 100)
_WEIGHTS = {
    "iv_term_structure": 25,
    "oi_gamma_concentration": 25,
    "intraday_flow": 15,
    "momentum_weakness": 20,
    "event_calendar": 10,
    "vix_regime": 5,
}


def _band(total: int) -> str:
    if total <= 30:
        return "Low"
    if total <= 50:
        return "Medium"
    if total <= 70:
        return "High"
    return "Extreme"


def _iv_term_score(bundle: SnapshotBundle) -> tuple[float, list[str]]:
    reasons: list[str] = []
    parts: list[float] = []

    # Front IV premium (primary signal)
    prem = bundle.front_iv_premium
    prem_score = _interp(prem, _IV_PREMIUM_THRESHOLDS)
    parts.append(prem_score * 0.65)
    if not np.isnan(prem) and prem > 0.20:
        reasons.append(
            f"{bundle.underlier} front IV premium +{prem:.0%} vs next week"
            + (" -- EXTREME backwardation" if prem > 0.50 else " -- HIGH backwardation" if prem > 0.35 else "")
        )

    # IV rank (secondary signal)
    if bundle.iv_rank is not None:
        rank_score = _interp(bundle.iv_rank, _IV_RANK_THRESHOLDS)
        parts.append(rank_score * 0.35)
        if bundle.iv_rank > 70:
            reasons.append(f"{bundle.underlier} IV rank {bundle.iv_rank:.0f}/100 -- elevated")
    else:
        parts.append(0.0)  # insufficient history

    return float(np.mean(parts) * 2) if parts else 0.0, reasons


def _oi_gamma_score(bundle: SnapshotBundle) -> tuple[float, list[str]]:
    reasons: list[str] = []
    parts: list[float] = []

    # OI vs 12-week baseline
    if bundle.oi_vs_baseline is not None:
        baseline_score = _interp(bundle.oi_vs_baseline, _OI_BASELINE_THRESHOLDS)
        parts.append(baseline_score * 0.5)
        if bundle.oi_vs_baseline >= 1.5:
            reasons.append(
                f"{bundle.underlier} Friday OI {bundle.oi_vs_baseline:.1f}x 12-week average"
            )
    else:
        parts.append(0.0)

    # Put/call OI ratio (elevated put buying = hedging activity)
    pcr = bundle.put_call_oi_ratio
    if not np.isnan(pcr):
        # PCR > 1.3 = elevated put demand; > 1.8 = panic-level
        pcr_score = float(np.clip((pcr - 0.8) / 1.0, 0, 1))
        parts.append(pcr_score * 0.3)
        if pcr > 1.3:
            reasons.append(f"{bundle.underlier} put/call OI ratio {pcr:.2f} -- elevated put demand")
    else:
        parts.append(0.0)

    # Gamma concentration (near-ATM OI as fraction of total)
    total = bundle.total_call_oi + bundle.total_put_oi
    if total > 0:
        conc = bundle.near_atm_oi / total
        conc_score = float(np.clip((conc - 0.15) / 0.25, 0, 1))
        parts.append(conc_score * 0.2)
    else:
        parts.append(0.0)

    return float(np.mean(parts) * 3) if parts else 0.0, reasons


def _flow_score(bundle: SnapshotBundle) -> tuple[float, list[str]]:
    reasons: list[str] = []
    voi = bundle.volume_oi_ratio
    score = _interp(voi, _VOL_OI_THRESHOLDS)
    if not np.isnan(voi) and voi > 0.5:
        reasons.append(f"{bundle.underlier} volume/OI {voi:.2f} -- high intraday activity")
    return score, reasons


def _vix_score(vix_current: float, vix_5d_change: float) -> tuple[float, list[str]]:
    reasons: list[str] = []
    level_score = _interp(vix_current, _VIX_LEVEL_THRESHOLDS)
    change_score = float(np.clip(vix_5d_change / 0.25, 0, 1)) if not np.isnan(vix_5d_change) else 0.0
    score = level_score * 0.6 + change_score * 0.4
    if vix_current > 22:
        reasons.append(f"VIX {vix_current:.1f} -- elevated volatility regime")
    if not np.isnan(vix_5d_change) and vix_5d_change > 0.15:
        reasons.append(f"VIX 5d change +{vix_5d_change:.0%} -- rising fear")
    return score, reasons


def compute_risk_score(
    bundles: list[SnapshotBundle],
    *,
    vix_current: float = float("nan"),
    vix_5d_change: float = float("nan"),
    momentum_fragility: float = 0.0,
    events: list[Event] | None = None,
    today: date | None = None,
) -> RiskScore:
    """Compute the 0-100 Momentum Crash Risk Score from all input signals."""
    if not bundles:
        return RiskScore(total=0, band="Low", components={}, reasons=["No data"])

    # --- IV term structure (25 pts) ---
    iv_scores: list[float] = []
    iv_reasons: list[str] = []
    for b in bundles:
        s, r = _iv_term_score(b)
        iv_scores.append(s)
        iv_reasons.extend(r)
    iv_component = float(np.mean(iv_scores)) if iv_scores else 0.0

    # --- OI / gamma concentration (25 pts) ---
    oi_scores: list[float] = []
    oi_reasons: list[str] = []
    for b in bundles:
        s, r = _oi_gamma_score(b)
        oi_scores.append(s)
        oi_reasons.extend(r)
    oi_component = float(np.mean(oi_scores)) if oi_scores else 0.0

    # --- Intraday flow (15 pts) ---
    flow_scores: list[float] = []
    flow_reasons: list[str] = []
    for b in bundles:
        s, r = _flow_score(b)
        flow_scores.append(s)
        flow_reasons.extend(r)
    flow_component = float(np.mean(flow_scores)) if flow_scores else 0.0

    # --- Momentum weakness (20 pts) ---
    momentum_component = float(np.clip(momentum_fragility, 0, 1))
    momentum_reasons: list[str] = []
    if momentum_fragility > 0.6:
        momentum_reasons.append("Momentum fragility elevated -- QQQ/SMH relative weakness + breadth narrowing")
    elif momentum_fragility > 0.35:
        momentum_reasons.append("Moderate momentum fragility -- monitor QQQ/SPY divergence")

    # --- Event calendar (10 pts) ---
    event_score = 0.0
    event_reasons: list[str] = []
    if events:
        for e in events:
            if e.importance == "HIGH":
                event_score = max(event_score, 0.8 if e.kind == "FOMC" else 0.6)
                event_reasons.append(f"{e.label} on {e.date}")
            elif e.importance == "MEDIUM":
                event_score = max(event_score, 0.3)
        event_component = float(np.clip(event_score, 0, 1))
    else:
        event_component = 0.0

    # --- VIX regime (5 pts) ---
    vix_component, vix_reasons = _vix_score(vix_current, vix_5d_change)

    # --- Weighted total ---
    w = _WEIGHTS
    total = round(
        iv_component * w["iv_term_structure"]
        + oi_component * w["oi_gamma_concentration"]
        + flow_component * w["intraday_flow"]
        + momentum_component * w["momentum_weakness"]
        + event_component * w["event_calendar"]
        + vix_component * w["vix_regime"]
    )
    total = max(0, min(100, total))

    components = {
        "iv_term_structure": round(iv_component, 3),
        "oi_gamma_concentration": round(oi_component, 3),
        "intraday_flow": round(flow_component, 3),
        "momentum_weakness": round(momentum_component, 3),
        "event_calendar": round(event_component, 3),
        "vix_regime": round(vix_component, 3),
    }

    all_reasons = iv_reasons + oi_reasons + flow_reasons + momentum_reasons + event_reasons + vix_reasons

    return RiskScore(
        total=total,
        band=_band(total),
        components=components,
        reasons=all_reasons,
    )
