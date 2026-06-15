from __future__ import annotations

from datetime import date

import pandas as pd

from hongquant.liquidity import store
from hongquant.liquidity.alerts import evaluate_alerts


def _daily(vals, end="2026-01-30"):
    idx = pd.bdate_range(end=end, periods=len(vals)).date
    return pd.Series([float(v) for v in vals], index=idx)


def test_hy_oas_widening_fires_credit_red(tmp_path):
    asof = date(2026, 1, 30)
    vals = [3.00, 3.00, 3.00, 3.00, 3.00, 3.10, 3.25, 3.40, 3.50, 3.55, 3.62]  # +62bp/10d
    store.write_vintages("BAMLH0A0HYM2", _daily(vals), as_of=asof, frequency="daily", root=tmp_path)
    rules = [{"id": 5, "name": "hy_oas_50bp_10d", "level": "credit_red",
              "kind": "change_bp", "series": "BAMLH0A0HYM2", "window": 10, "bp": 50, "downgrade": True}]
    out = evaluate_alerts(rules, as_of=asof, root=tmp_path)
    assert out[0].fired and out[0].triggers_downgrade


def test_hy_oas_calm_stays_silent(tmp_path):
    asof = date(2026, 1, 30)
    store.write_vintages("BAMLH0A0HYM2", _daily([3.00] * 11), as_of=asof, frequency="daily", root=tmp_path)
    rules = [{"id": 5, "name": "hy", "level": "credit_red",
              "kind": "change_bp", "series": "BAMLH0A0HYM2", "window": 10, "bp": 50, "downgrade": True}]
    out = evaluate_alerts(rules, as_of=asof, root=tmp_path)
    assert not out[0].fired


def test_sofr_iorb_spread_level_fires(tmp_path):
    asof = date(2026, 1, 30)
    store.write_vintages("SOFR", _daily([4.40] * 11), as_of=asof, frequency="daily", root=tmp_path)
    store.write_vintages("IORB", _daily([4.25] * 11), as_of=asof, frequency="daily", root=tmp_path)
    rules = [{"id": 2, "name": "sofr_iorb_10bp", "level": "plumbing_red",
              "kind": "spread_level_bp", "a": "SOFR", "b": "IORB", "bp": 10, "downgrade": True}]
    out = evaluate_alerts(rules, as_of=asof, root=tmp_path)
    assert out[0].fired  # 15bp >= 10bp


def test_missing_series_is_silent_not_error(tmp_path):
    rules = [{"id": 7, "name": "dollar", "level": "dollar_shock",
              "kind": "pct_change_up", "series": "DTWEXBGS", "window": 5, "pct": 2.5, "downgrade": False}]
    out = evaluate_alerts(rules, as_of=date(2026, 1, 30), root=tmp_path)
    assert not out[0].fired
