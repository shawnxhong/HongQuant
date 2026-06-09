from __future__ import annotations

from datetime import date

import pandas as pd

from hongquant.fragility import score as sc
from hongquant.fragility.systemic import gate_from_values
from hongquant.fragility.types import PillarScore, band_of

_TODAY = date(2026, 6, 9)
_NEUTRAL = gate_from_values()  # multiplier 1.0


def _score(a, b, c, *, gate=_NEUTRAL, sym="X"):
    return sc.compute_fragility(
        sym, _TODAY, gate=gate,
        pillar_a=PillarScore(a), pillar_b=PillarScore(b), pillar_c=PillarScore(c),
    )


def test_band_thresholds():
    assert band_of(0) == "Normal"
    assert band_of(39) == "Normal"
    assert band_of(40) == "Watch"
    assert band_of(59) == "Watch"
    assert band_of(60) == "Alert"
    assert band_of(74) == "Alert"
    assert band_of(75) == "Critical"
    assert band_of(100) == "Critical"


def test_all_high_pillars_score_high():
    s = _score(0.9, 0.9, 0.9)
    assert s.score > 80 and s.band == "Critical"


def test_any_pillar_near_zero_gates_score_down():
    # geometric mean: one ~0 pillar must crush the score even with the other two maxed
    gated = _score(0.95, 0.02, 0.95)
    assert gated.score < 30
    assert gated.score < _score(0.95, 0.95, 0.95).score


def test_missing_pillar_reduces_confidence_but_still_scores():
    s = _score(0.8, None, 0.8)
    assert s.confidence == round(2 / 3, 3)
    assert s.score > 0
    assert any("reduced confidence" in r for r in s.reasons)


def test_no_pillars_scores_zero():
    s = _score(None, None, None)
    assert s.score == 0 and s.band == "Normal"


def test_systemic_multiplier_bounds():
    calm = gate_from_values(nfci=-1.0, stlfsi=-2.0, vix_term=0.0)
    stormy = gate_from_values(nfci=2.0, stlfsi=5.0, vix_term=1.0)
    assert 0.80 <= calm.multiplier <= 1.30
    assert 0.80 <= stormy.multiplier <= 1.30
    assert stormy.multiplier > calm.multiplier


def test_systemic_multiplier_neutral_without_inputs():
    assert gate_from_values().multiplier == 1.0


def test_rank_and_flag_orders_by_score():
    scores = [_score(0.9, 0.9, 0.9, sym="HI"),
              _score(0.5, 0.5, 0.5, sym="MID"),
              _score(0.1, 0.1, 0.1, sym="LO")]
    sc.rank_and_flag(scores)
    by_rank = {s.symbol: s.rank for s in scores}
    assert by_rank["HI"] == 1 and by_rank["LO"] == 3


def test_attach_deltas_and_state_change():
    s = _score(0.9, 0.9, 0.9)  # ~Critical today
    hist = pd.Series({date(2026, 6, 4): 30.0, date(2026, 6, 5): 35.0, date(2026, 6, 6): 40.0})
    sc.attach_deltas(s, hist)
    assert s.delta_1d == round(s.score - 40.0, 1)
    assert s.delta_3d == round(s.score - 30.0, 1)
    assert sc.is_state_change(s, prev_band="Normal") is True   # band jumped up
    assert sc.is_state_change(_score(0.1, 0.1, 0.1), prev_band="Normal") is False


def test_first_sighting_at_watch_is_state_change():
    s = _score(0.6, 0.6, 0.6)  # Watch/Alert range
    assert sc.is_state_change(s, prev_band=None) is True
