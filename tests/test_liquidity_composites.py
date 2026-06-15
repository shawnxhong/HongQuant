from __future__ import annotations

from datetime import date

import pandas as pd

from hongquant.liquidity import store
from hongquant.liquidity.composites import compute_composite
from hongquant.liquidity.config_load import load_indicators
from hongquant.liquidity.types import IndicatorSpec


def _trend(n=900, end="2026-01-05"):
    idx = pd.bdate_range(end=end, periods=n).date
    return pd.Series([100 + 0.1 * i for i in range(n)], index=idx)


def test_config_weights_sum_to_one():
    ind = load_indicators()
    assert abs(sum(s.weight for s in ind.l_composite) - 1.0) < 1e-9
    assert abs(sum(s.weight for s in ind.r_composite) - 1.0) < 1e-9


def test_netliq_weight_cap_enforced():
    ind = load_indicators()
    netliq = next(s for s in ind.l_composite if s.key == "net_liquidity")
    assert netliq.weight <= 0.20  # spec §1.3 hard cap


def test_drop_and_renormalize(tmp_path):
    asof = date(2026, 1, 5)
    live = IndicatorSpec(
        key="a", label="A", source="fred", series="AA", op="delta",
        periods=5, sign=1, weight=0.7, frequency="daily",
    )
    dead = IndicatorSpec(
        key="b", label="B", source="finra", series="BB", op="level",
        periods=1, sign=1, weight=0.3, frequency="monthly", enabled=False,
    )
    store.write_vintages("AA", _trend(), as_of=asof, frequency="daily", root=tmp_path)

    res = compute_composite("L", [live, dead], as_of=asof, root=tmp_path)
    assert res.value is not None
    assert any(c.dropped for c in res.components)
    # renormalized over the single live 0.7-weight component => value == that component's x
    live_x = next(c.x for c in res.components if c.key == "a")
    assert abs(res.value - live_x) < 1e-9
    assert any("renormalized" in w for w in res.warnings)


def test_all_dropped_gives_none(tmp_path):
    dead = IndicatorSpec(
        key="b", label="B", source="finra", series="BB", op="level",
        periods=1, sign=1, weight=1.0, frequency="monthly", enabled=False,
    )
    res = compute_composite("R", [dead], as_of=date(2026, 1, 5), root=tmp_path)
    assert res.value is None
