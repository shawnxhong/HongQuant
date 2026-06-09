"""Multi-agent red team for the fragility radar (design §5).

A "Bull's Advocate" and a "Fragility Hawk" argue each flagged name; an
"Orchestrator" reconciles them into the daily briefing. Staged, bounded rounds
(three calls total) — no open-ended loop — so token use stays predictable.

Iron rule (design §5): the LLM **consumes** the pre-computed feature numbers and
**never invents** them. Every role is handed the deterministic DATA block as JSON
and instructed to cite only numbers present there. This keeps model hallucination
out of the signal — the numbers are always the pipeline's, the LLM only supplies
language, mechanism, and critique.
"""
from __future__ import annotations

import json
from datetime import date

from ...fragility.types import FragilityScore, SystemicGate
from ...logging import logger
from ...options.types import Event
from .. import client

_RULES = (
    "ABSOLUTE RULE: reference only numbers that appear in the DATA block below. "
    "Never invent, estimate, or recall figures from memory. If a number is not in "
    "DATA, describe it qualitatively or say it is unavailable. Scores are 0-100 "
    "conditional-fragility readings (higher = more fragile); pillars A/B/C are 0-1 "
    "(A=extension, B=crowding/leverage, C=dealer reflexivity). This system sizes "
    "positions and hedges — it does NOT time entries/exits. Be concise."
)

_BULL_SYS = (
    "You are the Bull's Advocate on a risk desk. Argue why the flagged names can "
    "keep trending and why today's fragility reading may overstate the danger. "
    "Steelman the long case from the DATA. " + _RULES
)
_HAWK_SYS = (
    "You are the Fragility Hawk on a risk desk. Argue why the flagged names are "
    "dangerously fragile: name the specific forced-deleveraging mechanism (dealer "
    "negative gamma, crowded leveraged longs, cluster cascade) that would turn an "
    "ordinary dip into a flash crash. " + _RULES
)
_ORCH_SYS = (
    "You are the Orchestrator on a risk desk. Given the Bull and Hawk arguments and "
    "the DATA, write a short daily briefing. For each flagged name: 2-3 sentences on "
    "why it is fragile and the mechanism that would drive forced selling; note any "
    "upcoming catalyst from DATA. End each name with one line: 'Falsified if: ...' "
    "(what would prove the fragility wrong). Reconcile where Bull and Hawk disagree. "
    + _RULES
)


def _data_block(
    scores: list[FragilityScore],
    events: list[Event],
    gate: SystemicGate,
) -> str:
    payload = {
        "market": {
            "systemic_multiplier": gate.multiplier,
            "nfci": gate.nfci,
            "stlfsi": gate.stlfsi,
            "vix_term_score_0_1": gate.vix_term,
        },
        "upcoming_catalysts": [
            {"date": e.date.isoformat(), "event": e.label, "importance": e.importance}
            for e in events
        ],
        "flagged_instruments": [
            {
                "symbol": s.symbol,
                "cluster": s.cluster,
                "fragility_score_0_100": s.score,
                "band": s.band,
                "pillar_A_extension_0_1": s.pillar_a,
                "pillar_B_crowding_0_1": s.pillar_b,
                "pillar_C_fragility_0_1": s.pillar_c,
                "cross_section_rank": s.rank,
                "delta_3d": s.delta_3d,
                "confidence": s.confidence,
                "feature_contributions": s.features,
                "triggered_signals": s.reasons,
            }
            for s in scores
        ],
    }
    return json.dumps(payload, indent=2, default=str)


def brief(
    scores: list[FragilityScore],
    *,
    events: list[Event] | None = None,
    gate: SystemicGate,
    today: date | None = None,
    model: str | None = None,
) -> str | None:
    """Run the staged red-team and return the Orchestrator's briefing (or None)."""
    if not scores or not client.is_enabled():
        return None

    data = _data_block(scores, events or [], gate)
    user = f"DATA:\n{data}"

    bull = client.complete(_BULL_SYS, user, model=model, max_tokens=1200)
    hawk = client.complete(_HAWK_SYS, user, model=model, max_tokens=1200)
    if bull is None and hawk is None:
        return None  # API unavailable — caller falls back to deterministic report

    synthesis_user = (
        f"DATA:\n{data}\n\n"
        f"BULL'S ADVOCATE:\n{bull or '(unavailable)'}\n\n"
        f"FRAGILITY HAWK:\n{hawk or '(unavailable)'}\n\n"
        "Write the reconciled briefing now."
    )
    out = client.complete(_ORCH_SYS, synthesis_user, model=model, max_tokens=2000)
    if out is None:
        logger.warning("Orchestrator call failed; returning Hawk view as fallback")
        return hawk
    return out
