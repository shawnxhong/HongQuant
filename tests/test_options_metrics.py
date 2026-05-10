from __future__ import annotations

from datetime import UTC, date, datetime

import numpy as np
import pandas as pd
import pytest

from hongquant.options import metrics as m

EXPIRY = date(2025, 5, 9)
SPOT = 500.0


def _chain(strikes_calls: list[tuple[float, int, float]], strikes_puts: list[tuple[float, int, float]]) -> pd.DataFrame:
    """Build a minimal chain DataFrame. (strike, OI, IV)"""
    rows = []
    now = datetime.now(tz=UTC)
    for strike, oi, iv in strikes_calls:
        rows.append({"underlier": "SPY", "expiration": EXPIRY, "strike": strike, "option_type": "call",
                         "bid": 1.0, "ask": 1.5, "last": 1.2, "volume": oi // 10,
                         "open_interest": oi, "implied_volatility": iv,
                         "delta": 0.5, "gamma": 0.01, "theta": -0.05, "vega": 0.2, "spot": SPOT, "snapshot_ts": now})
    for strike, oi, iv in strikes_puts:
        rows.append({"underlier": "SPY", "expiration": EXPIRY, "strike": strike, "option_type": "put",
                         "bid": 0.8, "ask": 1.2, "last": 1.0, "volume": oi // 10,
                         "open_interest": oi, "implied_volatility": iv,
                         "delta": -0.5, "gamma": 0.01, "theta": -0.05, "vega": 0.2, "spot": SPOT, "snapshot_ts": now})
    return pd.DataFrame(rows)


CALLS = [(490, 1000, 0.20), (500, 2000, 0.25), (510, 1500, 0.22), (520, 500, 0.21)]
PUTS = [(480, 800, 0.23), (490, 1200, 0.26), (500, 2500, 0.25), (510, 300, 0.20)]
CHAIN = _chain(CALLS, PUTS)


def test_atm_iv():
    iv = m.atm_iv(CHAIN, EXPIRY, SPOT)
    assert 0.20 < iv < 0.30


def test_atm_iv_empty():
    assert np.isnan(m.atm_iv(pd.DataFrame(), EXPIRY, SPOT))


def test_iv_term_structure_single_expiry():
    ts = m.iv_term_structure(CHAIN, SPOT)
    assert EXPIRY in ts
    assert 0.20 < ts[EXPIRY] < 0.30


def test_front_iv_premium():
    expiry2 = date(2025, 5, 16)
    calls2 = [(500, 1000, 0.35)]
    puts2 = [(500, 1000, 0.35)]
    chain2 = pd.concat([CHAIN, _chain(calls2, puts2)])
    chain2.loc[chain2["expiration"] == EXPIRY, "expiration"] = EXPIRY
    chain2.loc[chain2["expiration"] != EXPIRY, "expiration"] = expiry2

    prem = m.front_iv_premium(chain2, SPOT, EXPIRY, expiry2)
    assert isinstance(prem, float)


def test_total_oi():
    oi = m.total_oi(CHAIN, EXPIRY)
    assert oi["call"] == 1000 + 2000 + 1500 + 500
    assert oi["put"] == 800 + 1200 + 2500 + 300
    assert oi["total"] == oi["call"] + oi["put"]
    assert oi["put_call_ratio"] == pytest.approx(oi["put"] / oi["call"], rel=1e-6)


def test_near_atm_oi():
    near = m.near_atm_oi(CHAIN, EXPIRY, SPOT, pct=0.02)
    # Strikes within ±2% of 500: [490, 500, 510] (490=500*0.98, 510=500*1.02)
    assert near > 0


def test_volume_oi_ratio():
    ratio = m.volume_oi_ratio(CHAIN, EXPIRY)
    assert 0 < ratio < 1


def test_gamma_exposure_by_strike():
    gex = m.gamma_exposure_by_strike(CHAIN, EXPIRY, SPOT)
    assert "strike" in gex.columns
    assert "call_gex" in gex.columns
    assert "put_gex" in gex.columns
    assert "net_gex" in gex.columns
    assert len(gex) > 0
    assert all(gex["call_gex"] >= 0)


def test_call_wall():
    cw = m.call_wall(CHAIN, EXPIRY, SPOT)
    assert cw > SPOT  # call wall is above spot


def test_put_wall():
    pw = m.put_wall(CHAIN, EXPIRY, SPOT)
    assert pw < SPOT  # put wall is below spot


def test_max_pain():
    mp = m.max_pain(CHAIN, EXPIRY)
    strikes = CHAIN["strike"].unique()
    assert mp in strikes


def test_expected_move():
    em = m.expected_move(CHAIN, EXPIRY, SPOT)
    assert 0 < em < 0.5  # sanity: 0-50% expected move


def test_oi_vs_baseline():
    history = pd.Series([4000.0, 4200.0, 3800.0, 4100.0])
    result = m.oi_vs_baseline(6000, history)
    assert result is not None
    assert result > 1.0  # 6000 / ~4025 ≈ 1.49


def test_oi_vs_baseline_insufficient():
    assert m.oi_vs_baseline(1000, pd.Series([1000.0, 1000.0])) is None


def test_iv_rank():
    history = pd.Series([0.15, 0.18, 0.20, 0.22, 0.25, 0.30])
    rank = m.iv_rank(0.25, history)
    assert rank is not None
    assert 0 <= rank <= 100
    # 0.25 is near the top of this history
    assert rank > 60


def test_iv_rank_insufficient():
    assert m.iv_rank(0.25, pd.Series([0.20, 0.22])) is None
