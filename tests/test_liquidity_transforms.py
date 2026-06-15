from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from hongquant.liquidity.transforms import apply_op, delta, rolling_z


def test_delta_and_pct_change():
    s = pd.Series([1.0, 2.0, 4.0, 7.0])
    assert delta(s, 1).iloc[-1] == 3.0
    assert apply_op(s, "pct_change", 1).iloc[-1] == pytest.approx(0.75)


def test_rolling_z_clips_outlier():
    s = pd.Series([*range(100), 1000.0])
    assert rolling_z(s, window=50, min_periods=10, clip=2.0) == 2.0


def test_rolling_z_short_history_is_nan():
    assert np.isnan(rolling_z(pd.Series([1.0, 2.0]), window=50, min_periods=10))


def test_apply_op_rejects_unknown():
    with pytest.raises(ValueError):
        apply_op(pd.Series([1.0]), "bogus", 1)
