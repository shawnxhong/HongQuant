from __future__ import annotations

from datetime import date

from hongquant.fragility import actions
from hongquant.fragility.score import compute_fragility
from hongquant.fragility.systemic import gate_from_values
from hongquant.fragility.types import PillarScore


def _score(a, b, c):
    return compute_fragility(
        "X", date(2026, 6, 9), gate=gate_from_values(),
        pillar_a=PillarScore(a), pillar_b=PillarScore(b), pillar_c=PillarScore(c),
    )


def test_recommendation_has_three_parts():
    rec = actions.recommendation(_score(0.9, 0.9, 0.9))
    assert set(rec) == {"posture", "falsification", "base_rate"}
    assert rec["posture"]  # non-empty


def test_falsification_targets_dominant_pillar():
    # extension-dominant -> falsifier mentions the 50dma path
    rec = actions.recommendation(_score(0.95, 0.2, 0.2))
    assert "50dma" in rec["falsification"]
    # fragility-dominant -> falsifier mentions dealer gamma / term structure
    rec_c = actions.recommendation(_score(0.2, 0.2, 0.95))
    assert "gamma" in rec_c["falsification"]


def test_base_rate_placeholder_without_ledger():
    rec = actions.recommendation(_score(0.9, 0.9, 0.9))
    assert "calibration pending" in rec["base_rate"]


def test_base_rate_uses_ledger_when_present():
    s = _score(0.9, 0.9, 0.9)
    stats = {s.band: {"hit_rate": 0.22, "n": 18}}
    note = actions.base_rate_note(s.band, stats)
    assert "22%" in note and "n=18" in note


def test_posture_escalates_with_band():
    assert actions.POSTURE["Normal"] != actions.POSTURE["Critical"]
    assert "hedge" in actions.POSTURE["Critical"].lower()
