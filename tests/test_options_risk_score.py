from __future__ import annotations

from datetime import UTC, date, datetime

import pandas as pd

from hongquant.options.risk_score import compute_risk_score
from hongquant.options.types import Event, SnapshotBundle


def _bundle(
    underlier: str = "QQQ",
    spot: float = 490.0,
    front_iv_premium: float = 0.0,
    oi_vs_baseline: float | None = None,
    volume_oi_ratio: float = 0.1,
    put_call_oi_ratio: float = 0.8,
    iv_rank: float | None = None,
    total_call_oi: int = 100_000,
    total_put_oi: int = 80_000,
) -> SnapshotBundle:
    return SnapshotBundle(
        underlier=underlier,
        spot=spot,
        snapshot_ts=datetime.now(tz=UTC),
        chain=pd.DataFrame(),
        front_expiry=date(2025, 5, 9),
        next_expiry=date(2025, 5, 16),
        front_atm_iv=0.25 * (1 + front_iv_premium),
        next_atm_iv=0.25,
        front_iv_premium=front_iv_premium,
        iv_rank=iv_rank,
        total_call_oi=total_call_oi,
        total_put_oi=total_put_oi,
        put_call_oi_ratio=put_call_oi_ratio,
        volume_oi_ratio=volume_oi_ratio,
        near_atm_oi=10_000,
        call_wall=500.0,
        put_wall=480.0,
        max_pain=492.0,
        expected_move=0.02,
        gamma_by_strike=pd.DataFrame(),
        oi_vs_baseline=oi_vs_baseline,
    )


def test_low_risk_all_normal():
    score = compute_risk_score(
        [_bundle(front_iv_premium=0.05, oi_vs_baseline=1.0)],
        vix_current=14.0,
        vix_5d_change=-0.05,
        momentum_fragility=0.0,
        events=[],
    )
    assert score.band == "Low"
    assert score.total <= 30


def test_high_risk_iv_spike():
    score = compute_risk_score(
        [_bundle(front_iv_premium=0.38, iv_rank=82.0, oi_vs_baseline=1.7,
                 volume_oi_ratio=0.6)],
        vix_current=26.0,
        vix_5d_change=0.18,
        momentum_fragility=0.65,
        events=[Event(date=date(2025, 5, 7), kind="FOMC", label="FOMC", importance="HIGH")],
    )
    assert score.band in ("High", "Extreme")
    assert score.total >= 51
    assert len(score.reasons) > 0


def test_extreme_risk():
    score = compute_risk_score(
        [_bundle(front_iv_premium=0.55, iv_rank=92.0, oi_vs_baseline=2.2,
                 volume_oi_ratio=0.9, put_call_oi_ratio=1.8)],
        vix_current=35.0,
        vix_5d_change=0.30,
        momentum_fragility=0.95,
        events=[Event(date=date(2025, 5, 7), kind="FOMC", label="FOMC", importance="HIGH")],
    )
    assert score.band == "Extreme"
    assert score.total >= 71


def test_medium_risk():
    score = compute_risk_score(
        [_bundle(front_iv_premium=0.28, iv_rank=65.0, oi_vs_baseline=1.65,
                 volume_oi_ratio=0.35)],
        vix_current=22.0,
        vix_5d_change=0.15,
        momentum_fragility=0.4,
        events=[Event(date=date(2025, 5, 13), kind="CPI", label="CPI", importance="HIGH")],
    )
    assert score.band in ("Medium", "High")
    assert 31 <= score.total <= 70


def test_no_bundles():
    score = compute_risk_score([])
    assert score.band == "Low"
    assert score.total == 0


def test_score_components_present():
    score = compute_risk_score([_bundle()])
    expected_keys = {"iv_term_structure", "oi_gamma_concentration", "intraday_flow",
                     "momentum_weakness", "event_calendar", "vix_regime"}
    assert expected_keys == set(score.components.keys())
    assert all(0.0 <= v <= 1.0 for v in score.components.values())


def test_iv_backwardation_reason_appears():
    score = compute_risk_score(
        [_bundle(front_iv_premium=0.45)],
        vix_current=15.0, vix_5d_change=0.0, momentum_fragility=0.0,
    )
    reason_text = " ".join(score.reasons).lower()
    assert "iv" in reason_text or "premium" in reason_text
