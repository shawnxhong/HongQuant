from __future__ import annotations

import numpy as np
import pandas as pd

from hongquant.fragility import normalize as nz


def test_pct_rank_rising_series_is_extreme():
    s = pd.Series(np.linspace(0, 1, 300))
    assert nz.pct_rank(s) > 0.98  # latest value is the highest in its history


def test_pct_rank_midpoint_is_middling():
    s = pd.Series([*range(300), 150])  # last value sits in the middle
    assert 0.3 < nz.pct_rank(s) < 0.7


def test_pct_rank_short_history_is_nan():
    assert np.isnan(nz.pct_rank(pd.Series([1, 2, 3])))


def test_pct_rank_flat_series_is_half():
    assert nz.pct_rank(pd.Series([5.0] * 200)) == 0.5


def test_robust_z_symmetric_and_clipped():
    s = pd.Series([*range(200), 10_000])  # extreme last value
    assert nz.robust_z(s) == 3.0  # clipped to the ceiling
    assert -3.0 <= nz.robust_z(pd.Series([*range(200), 100])) <= 3.0


def test_scale_unit_clamps():
    assert nz.scale_unit(5, 0, 10) == 0.5
    assert nz.scale_unit(-1, 0, 10) == 0.0
    assert nz.scale_unit(99, 0, 10) == 1.0
    assert np.isnan(nz.scale_unit(float("nan"), 0, 10))


def test_weighted_mean_renormalizes_over_available():
    parts = {"a": 1.0, "b": None, "c": 0.0}
    weights = {"a": 0.5, "b": 0.3, "c": 0.2}
    # b is missing → weights renormalize over a and c: (0.5*1 + 0.2*0) / 0.7
    assert abs(nz.weighted_mean(parts, weights) - (0.5 / 0.7)) < 1e-9


def test_weighted_mean_all_missing_is_none():
    assert nz.weighted_mean({"a": None}, {"a": 1.0}) is None


def test_winsorize_clips_tails():
    s = pd.Series([*range(100), 10_000])
    w = nz.winsorize(s, 0.05, 0.95)
    assert w.max() < 10_000
