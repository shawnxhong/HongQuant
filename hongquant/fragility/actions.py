"""Band → position/hedge posture, with a falsification companion (design §6, §7).

Every output is framed as a *position-sizing / hedging* knob, never entry/exit
timing — that line is the system's whole discipline (design §0, §10). Each alert
also ships a "falsification companion" (what would make this a false positive)
and a base-rate slot that, once the live ledger has accumulated, shows how often
this band actually preceded a flash crash.
"""
from __future__ import annotations

from .types import Band, FragilityScore

POSTURE: dict[Band, str] = {
    "Normal": "Maintain. Normal conditions — no fragility-driven action.",
    "Watch": "Tighten mental stops and pause adds on this name. No forced action yet.",
    "Alert": "Trim ~20-40% of the position or buy cheap OTM put protection. "
             "Do not add.",
    "Critical": "Cut to a core position and add a hedge. No new exposure until "
                "dealer positioning / IV crush clears.",
}

_PILLAR_FALSIFIERS = {
    "a": "if price consolidates sideways or eases back toward its 50dma without "
         "a volume spike, the extension resolves on its own",
    "b": "if the IV-RV spread re-widens (insurance re-prices) or crowded longs "
         "unwind, the crowding fuel drains",
    "c": "if dealer gamma flips back positive or the VIX term structure "
         "re-contangos, the reflexive sell-amplifier switches off",
}


def _dominant_pillar(score: FragilityScore) -> str | None:
    vals = {"a": score.pillar_a, "b": score.pillar_b, "c": score.pillar_c}
    present = {k: v for k, v in vals.items() if v is not None}
    if not present:
        return None
    return max(present, key=lambda k: present[k])


def falsification(score: FragilityScore) -> str:
    """What would make today's reading a false positive (design §6 证伪伴侣)."""
    dom = _dominant_pillar(score)
    lead = _PILLAR_FALSIFIERS.get(dom, "if the driving signal mean-reverts")
    return (
        f"False-positive check: {lead}. Low-vol complacency can persist for "
        "months — this is conditional fragility, not a timing signal."
    )


def base_rate_note(band: Band, ledger_stats: dict | None = None) -> str:
    """Running precision for this band, or a placeholder until the ledger fills (design §7)."""
    if ledger_stats and band in ledger_stats:
        s = ledger_stats[band]
        return (
            f"Base rate: {s['hit_rate']:.0%} of past '{band}' readings preceded a "
            f"≥X% drawdown within 10 sessions (n={s['n']})."
        )
    return "Base rate: calibration pending — the live ledger is still accumulating."


def recommendation(score: FragilityScore, ledger_stats: dict | None = None) -> dict[str, str]:
    """Bundle posture + falsification + base-rate note for one instrument."""
    return {
        "posture": POSTURE[score.band],
        "falsification": falsification(score),
        "base_rate": base_rate_note(score.band, ledger_stats),
    }
