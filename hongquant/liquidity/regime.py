"""Mechanical regime state machine (spec §4.2-4.3).

Each of L and R carries its own direction (up/down) with hysteresis: a flip needs
either one strong month (|score| ≥ strong_confirm) or two consecutive same-sign
months (|score| ≥ two_month_confirm); inside the neutral band the prior direction
holds. The quadrant is the combination of the two directions. A red interrupt can
*suggest* a one-step downgrade, but that is provisional and requires human
confirmation (spec §4.2) — it is never auto-applied to the persisted quadrant.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any

from .types import Direction, Quadrant, RegimeState, WaterLevel

_QUADRANT: dict[tuple[Direction, Direction], Quadrant] = {
    ("up", "up"): "Q1",
    ("up", "down"): "Q2",
    ("down", "up"): "Q3",
    ("down", "down"): "Q4",
}
# One-step emergency downgrade ladder (spec §4.2 "Q1→Q2/Q3, Q2/Q3→Q4").
_DOWNGRADE: dict[Quadrant, Quadrant] = {"Q1": "Q3", "Q2": "Q4", "Q3": "Q4", "Q4": "Q4"}


def update_direction(
    score: float | None,
    prev_dir: Direction | None,
    prev_score: float | None,
    *,
    neutral: float,
    strong: float,
    two_month: float,
) -> Direction:
    """Apply the hysteresis rule to one dimension's direction."""
    if score is None or not math.isfinite(score):
        return prev_dir or "down"  # no reading -> hold; conservative cold start
    if prev_dir is None:
        return "up" if score >= 0 else "down"

    raw = 1 if score >= neutral else (-1 if score <= -neutral else 0)
    cur = 1 if prev_dir == "up" else -1
    if raw == 0 or raw == cur:
        return prev_dir  # neutral band holds; same-sign confirms

    strong_ok = abs(score) >= strong
    prev_ok = prev_score is not None and math.isfinite(prev_score)
    two_ok = prev_ok and abs(score) >= two_month and (
        prev_score >= two_month if raw == 1 else prev_score <= -two_month
    )
    if strong_ok or two_ok:
        return "up" if raw == 1 else "down"
    return prev_dir


def quadrant_of(l_dir: Direction, r_dir: Direction) -> Quadrant:
    return _QUADRANT[(l_dir, r_dir)]


def suggest_downgrade(quadrant: Quadrant) -> Quadrant:
    """The provisional one-step downgrade a red interrupt would recommend."""
    return _DOWNGRADE[quadrant]


def water_level_for(quadrant: Quadrant, water_levels: dict[str, dict[str, float]]) -> WaterLevel:
    wl = water_levels.get(quadrant, {})
    return WaterLevel(
        sleeve_max_pct=float(wl.get("sleeve_max_pct", 5)),
        leverage_max=float(wl.get("leverage_max", 1.0)),
        fragility_mult=float(wl.get("fragility_mult", 1.5)),
    )


def compute_regime(
    *,
    asof: date,
    l_score: float | None,
    r_score: float | None,
    prior: dict[str, Any] | None,
    state_machine: dict[str, Any],
    water_levels: dict[str, dict[str, float]],
) -> RegimeState:
    """Run the state machine for one monthly run, given the prior state card."""
    neutral = float(state_machine.get("neutral_band", 0.25))
    strong = float(state_machine.get("strong_confirm", 0.50))
    two_month = float(state_machine.get("two_month_confirm", 0.25))

    prev_l_dir = prior.get("l_direction") if prior else None
    prev_r_dir = prior.get("r_direction") if prior else None
    prev_l_score = prior.get("L_score") if prior else None
    prev_r_score = prior.get("R_score") if prior else None

    l_dir = update_direction(
        l_score, prev_l_dir, prev_l_score, neutral=neutral, strong=strong, two_month=two_month
    )
    r_dir = update_direction(
        r_score, prev_r_dir, prev_r_score, neutral=neutral, strong=strong, two_month=two_month
    )
    quadrant = quadrant_of(l_dir, r_dir)

    notes: list[str] = []
    if l_score is None:
        notes.append("L unavailable — held prior direction")
    if r_score is None:
        notes.append("R unavailable — held prior direction")
    if prior and prior.get("quadrant") and prior["quadrant"] != quadrant:
        notes.append(f"quadrant moved {prior['quadrant']} → {quadrant}")

    return RegimeState(
        asof=asof,
        quadrant=quadrant,
        provisional=False,
        l_score=l_score,
        r_score=r_score,
        l_direction=l_dir,
        r_direction=r_dir,
        water_level=water_level_for(quadrant, water_levels),
        notes=notes,
    )
