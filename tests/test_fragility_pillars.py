from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from hongquant.fragility import crowding, extension
from hongquant.fragility import fragility_pillar as cpillar
from hongquant.fragility.types import InstrumentFeatures

_EXPIRY = date(2026, 6, 19)


def _closes(scale: float, n: int = 300) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=n, freq="B").date
    return pd.Series(np.exp(np.linspace(0, scale, n)), index=idx)


def _chain(*, spot=100.0, call_oi=1000, put_oi=1000, iv=0.30, gamma=0.02) -> pd.DataFrame:
    rows = []
    for k in range(int(spot * 0.8), int(spot * 1.2) + 1, 5):
        for ot, oi in (("call", call_oi), ("put", put_oi)):
            rows.append(
                {"underlier": "X", "expiration": _EXPIRY, "strike": float(k),
                 "option_type": ot, "bid": 1.0, "ask": 1.2, "last": 1.1, "volume": 10,
                 "open_interest": oi, "implied_volatility": iv, "delta": 0.5,
                 "gamma": gamma, "theta": -0.1, "vega": 0.1, "spot": spot}
            )
    return pd.DataFrame(rows)


# --- Pillar A: Extension --------------------------------------------------

def test_extension_high_for_parabolic_trend():
    ps = extension.compute(_closes(0.8))
    assert ps.value is not None and ps.value > 0.6


def test_extension_low_after_pullback():
    # rise for 250 sessions, then a sharp 30% washout — current reading is the
    # most stretched-to-the-downside in its own history, so extension is low.
    idx = pd.date_range("2024-01-01", periods=300, freq="B").date
    up = np.exp(np.linspace(0, 0.6, 250))
    down = up[-1] * np.exp(np.linspace(0, -0.35, 50))
    ps = extension.compute(pd.Series(np.concatenate([up, down]), index=idx))
    assert ps.value is not None and ps.value < 0.4


def test_extension_flat_series_is_neutral_not_high():
    flat = pd.Series([100.0] * 300, index=pd.date_range("2024-01-01", periods=300, freq="B").date)
    ps = extension.compute(flat)
    assert ps.value is not None and ps.value < 0.55  # neutral — not flagged as stretched


def test_extension_none_for_short_history():
    assert extension.compute(pd.Series([1.0, 2.0, 3.0])).value is None


# --- Pillar B: Crowding ---------------------------------------------------

def test_crowding_none_without_options_or_cot():
    feat = InstrumentFeatures(symbol="X", asof=date.today(), closes=_closes(0.2))
    assert crowding.compute(feat).value is None


def test_crowding_rises_with_call_heavy_chain():
    closes = _closes(0.2)
    feat = InstrumentFeatures(
        symbol="X", asof=date.today(), closes=closes, spot=100.0,
        chain=_chain(call_oi=4000, put_oi=1000, iv=0.10), front_expiry=_EXPIRY,
    )
    ps = crowding.compute(feat)
    assert ps.value is not None
    assert ps.features.get("call_share", 0) > 0.5  # call-heavy registers


def test_crowding_uses_cot_when_present():
    cot = pd.Series(np.linspace(-1000, 5000, 200))  # managed money very long now
    feat = InstrumentFeatures(symbol="GLD", asof=date.today(), closes=_closes(0.2), cot_net=cot)
    ps = crowding.compute(feat)
    assert ps.value is not None and ps.features.get("cot_mm_net", 0) > 0.9


# --- Pillar C: Fragility --------------------------------------------------

def test_gamma_regime_high_when_dealers_short_gamma():
    # heavier put gamma => negative net GEX => dealers short gamma => fragile
    score = cpillar.gamma_regime_score(_chain(call_oi=1000, put_oi=3000), _EXPIRY, 100.0)
    assert score is not None and score > 0.6


def test_gamma_regime_low_when_long_gamma():
    score = cpillar.gamma_regime_score(_chain(call_oi=3000, put_oi=1000), _EXPIRY, 100.0)
    assert score is not None and score < 0.4


def test_vix_term_backwardation_scores_high():
    assert cpillar.vix_term_score(vix=25, vix3m=22, vix9d=27) > 0.6  # front > back
    assert cpillar.vix_term_score(vix=15, vix3m=18, vix9d=14) < 0.4  # contango


def test_fragility_pillar_combines_market_and_cluster():
    feat = InstrumentFeatures(
        symbol="X", asof=date.today(), spot=100.0,
        chain=_chain(call_oi=1000, put_oi=3000), front_expiry=_EXPIRY,
        cluster="ai_semis", cluster_corr_pctile=0.95,
    )
    market = {"vix_term": 0.8, "vvix": 0.7, "skew": 0.6}
    ps = cpillar.compute(feat, market)
    assert ps.value is not None and ps.value > 0.5
    assert any("cascade" in r for r in ps.reasons)
