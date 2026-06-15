from __future__ import annotations

from datetime import date

from hongquant.liquidity.regime import (
    compute_regime,
    quadrant_of,
    suggest_downgrade,
    update_direction,
    water_level_for,
)

SM = {"neutral_band": 0.25, "strong_confirm": 0.50, "two_month_confirm": 0.25}
WL = {
    "Q1": {"sleeve_max_pct": 15, "leverage_max": 1.2, "fragility_mult": 1.0},
    "Q2": {"sleeve_max_pct": 10, "leverage_max": 1.0, "fragility_mult": 1.0},
    "Q3": {"sleeve_max_pct": 10, "leverage_max": 1.0, "fragility_mult": 1.5},
    "Q4": {"sleeve_max_pct": 5, "leverage_max": 1.0, "fragility_mult": 1.5},
}


def _upd(score, prev, prev_score):
    return update_direction(score, prev, prev_score, neutral=0.25, strong=0.50, two_month=0.25)


def test_neutral_band_holds_prior():
    assert _upd(0.1, "up", 0.6) == "up"
    assert _upd(-0.1, "down", -0.6) == "down"


def test_single_strong_month_flips():
    assert _upd(-0.6, "up", 0.6) == "down"


def test_single_weak_opposing_does_not_flip():
    assert _upd(-0.30, "up", 0.6) == "up"


def test_two_consecutive_opposing_months_flip():
    assert _upd(-0.30, "up", -0.30) == "down"


def test_quadrant_mapping():
    assert quadrant_of("up", "up") == "Q1"
    assert quadrant_of("up", "down") == "Q2"
    assert quadrant_of("down", "up") == "Q3"
    assert quadrant_of("down", "down") == "Q4"


def test_water_level_lookup():
    assert water_level_for("Q3", WL).fragility_mult == 1.5
    assert water_level_for("Q4", WL).sleeve_max_pct == 5


def test_downgrade_ladder():
    assert suggest_downgrade("Q1") == "Q3"
    assert suggest_downgrade("Q2") == "Q4"
    assert suggest_downgrade("Q4") == "Q4"


def test_compute_regime_cold_start():
    r = compute_regime(
        asof=date(2026, 1, 1), l_score=0.6, r_score=-0.6,
        prior=None, state_machine=SM, water_levels=WL,
    )
    assert r.quadrant == "Q2"
    assert r.l_direction == "up" and r.r_direction == "down"
    assert r.water_level.sleeve_max_pct == 10


def test_compute_regime_holds_quadrant_in_dead_band():
    prior = {"quadrant": "Q1", "l_direction": "up", "r_direction": "up", "L_score": 0.6, "R_score": 0.6}
    r = compute_regime(
        asof=date(2026, 2, 1), l_score=0.1, r_score=0.1,
        prior=prior, state_machine=SM, water_levels=WL,
    )
    assert r.quadrant == "Q1"  # dead band -> hold
