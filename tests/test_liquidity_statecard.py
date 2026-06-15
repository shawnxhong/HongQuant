from __future__ import annotations

from datetime import date

from hongquant.liquidity import statecard
from hongquant.liquidity.types import (
    Alert,
    ComponentValue,
    CompositeResult,
    RegimeState,
    WaterLevel,
)

_CONTRACT_KEYS = {
    "system", "version", "as_of", "run_id", "quadrant", "quadrant_provisional",
    "L_score", "R_score", "water_level", "reaction_function", "alerts_active",
    "data_vintages", "analyst_dissent",
}


def _regime():
    return RegimeState(
        asof=date(2026, 6, 27), quadrant="Q3", provisional=False,
        l_score=-0.42, r_score=0.31, l_direction="down", r_direction="up",
        water_level=WaterLevel(sleeve_max_pct=10, leverage_max=1.0, fragility_mult=1.5),
    )


def test_state_card_matches_contract(tmp_path):
    lres = CompositeResult("L", -0.42, [ComponentValue("real_rate", "RR", 0.25, x=-0.5)])
    rres = CompositeResult("R", 0.31, [ComponentValue("hy_oas", "HY", 0.35, x=0.4)])
    alerts = [Alert(9, "carry_divergence", "carry_divergence", fired=True, message="...")]

    card = statecard.build_state_card(
        regime=_regime(), l_result=lres, r_result=rres, alerts=alerts,
        reaction_function={"status": None, "fed_vs_market_gap_bps": -38},
    )

    assert _CONTRACT_KEYS <= set(card)
    assert card["quadrant"] == "Q3"
    assert card["water_level"]["fragility_alert_multiplier"] == 1.5
    assert card["alerts_active"] == ["carry_divergence"]

    path = statecard.write_state_card(card, root=tmp_path)
    assert path.exists()
    back = statecard.read_latest(root=tmp_path)
    assert back["run_id"] == "lrm-2026-06"
    assert (tmp_path / "state" / "lrm" / "lrm-2026-06.json").exists()


def test_read_latest_cold_start(tmp_path):
    assert statecard.read_latest(root=tmp_path) is None
