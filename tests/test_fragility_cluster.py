from __future__ import annotations

import numpy as np
import pandas as pd

from hongquant.fragility import cluster


def _series(values: np.ndarray) -> pd.Series:
    idx = pd.date_range("2024-01-01", periods=len(values), freq="B").date
    return pd.Series(values, index=idx)


def test_correlated_cluster_has_high_latest_correlation():
    rng = np.random.RandomState(0)
    base = np.cumsum(rng.normal(0, 1, 300)) + 100
    members = {f"S{i}": _series(base + rng.normal(0, 0.2, 300)) for i in range(4)}
    latest, _ = cluster.cluster_signal(members, window=20)
    assert latest is not None and latest > 0.7


def test_uncorrelated_cluster_has_low_latest_correlation():
    rng = np.random.RandomState(1)
    members = {
        f"S{i}": _series(np.cumsum(rng.normal(0, 1, 300)) + 100) for i in range(4)
    }
    latest, _ = cluster.cluster_signal(members, window=20)
    assert latest is not None and abs(latest) < 0.5


def test_single_member_cluster_returns_none():
    members = {"ONLY": _series(np.arange(300.0))}
    assert cluster.cluster_signal(members) == (None, None)
