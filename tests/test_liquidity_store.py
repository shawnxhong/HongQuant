from __future__ import annotations

from datetime import date

import pandas as pd

from hongquant.liquidity import store


def _series(vals, start="2026-01-01"):
    idx = pd.bdate_range(start=start, periods=len(vals)).date
    return pd.Series([float(v) for v in vals], index=idx)


def test_vintage_round_trip(tmp_path):
    store.write_vintages("X", _series([1, 2, 3]), as_of=date(2026, 1, 9), frequency="daily", root=tmp_path)
    out = store.read_series_asof("X", as_of=date(2026, 1, 9), root=tmp_path)
    assert len(out) == 3 and out.iloc[-1] == 3.0


def test_point_in_time_ignores_future_asof(tmp_path):
    # First vintage: obs 1/1, 1/2, 1/5 known as of 1/6.
    store.write_vintages("X", _series([1, 2, 3]), as_of=date(2026, 1, 6), frequency="daily", root=tmp_path)
    # Later vintage (as of 1/13) revises 1/5 and adds 1/6, 1/7.
    revised = pd.Series(
        [9.0, 4.0, 5.0],
        index=[date(2026, 1, 5), date(2026, 1, 6), date(2026, 1, 7)],
    )
    store.write_vintages("X", revised, as_of=date(2026, 1, 13), frequency="daily", root=tmp_path)

    asof6 = store.read_series_asof("X", as_of=date(2026, 1, 6), root=tmp_path)
    assert asof6.loc[date(2026, 1, 5)] == 3.0       # original, not the 1/13 revision
    assert date(2026, 1, 7) not in asof6.index       # future observation invisible

    asof13 = store.read_series_asof("X", as_of=date(2026, 1, 13), root=tmp_path)
    assert asof13.loc[date(2026, 1, 5)] == 9.0       # revision now visible
    assert asof13.loc[date(2026, 1, 7)] == 5.0


def test_staleness_and_cold_start(tmp_path):
    assert store.read_series_asof("nope", as_of=date(2026, 1, 1), root=tmp_path).empty
    assert store.staleness_days("nope", as_of=date(2026, 1, 1), root=tmp_path) is None
    store.write_vintages("X", _series([1, 2], start="2026-01-01"), as_of=date(2026, 1, 12), frequency="daily", root=tmp_path)
    # last obs is the 2nd business day on/after 2026-01-01 = 2026-01-02
    assert store.staleness_days("X", as_of=date(2026, 1, 12), root=tmp_path) == 10
