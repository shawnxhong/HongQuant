"""L and R composite scores (spec §4.1) with drop-and-renormalize.

For each component: read its point-in-time series, apply the signed transform,
take the 5y rolling z-score clipped to ±2, and multiply by the component sign so
positive = expansion / risk-on. A component whose source is stale, empty, or
disabled is dropped and the remaining weights renormalize, with an explicit
warning surfaced to the report (spec §3 data-quality rule).
"""
from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np

from . import quality
from .series import resolve_series
from .transforms import apply_op, rolling_z
from .types import ComponentValue, CompositeResult, IndicatorSpec


def _component(
    spec: IndicatorSpec,
    *,
    as_of: date,
    root: Path | None,
    globalcb_weights: dict[str, float],
    staleness_budgets: dict[str, int],
) -> ComponentValue:
    cv = ComponentValue(key=spec.key, label=spec.label, weight=spec.weight)
    if not spec.enabled:
        cv.dropped, cv.reason = True, "disabled (deferred source)"
        return cv

    raw = resolve_series(spec, as_of=as_of, root=root, globalcb_weights=globalcb_weights)
    if raw is None or raw.empty:
        cv.dropped, cv.reason = True, "no data"
        return cv

    stale_days = (as_of - max(raw.index)).days
    budget = quality.staleness_budget(spec.key, staleness_budgets)
    if quality.is_stale(stale_days, budget):
        cv.dropped, cv.reason = True, f"stale {stale_days}d > {budget}d budget"
        return cv

    transformed = apply_op(raw, spec.op, spec.periods)
    window, min_periods = spec.z_window()
    z = rolling_z(transformed, window=window, min_periods=min_periods)
    if not math.isfinite(z):
        cv.dropped, cv.reason = True, "insufficient history for 5y z-score"
        return cv

    cv.x = float(np.clip(z, -2.0, 2.0) * spec.sign)
    if spec.proxy:
        cv.reason = "proxy source"
    return cv


def compute_composite(
    name: str,
    specs: list[IndicatorSpec],
    *,
    as_of: date,
    root: Path | None = None,
    globalcb_weights: dict[str, float] | None = None,
    staleness_budgets: dict[str, int] | None = None,
) -> CompositeResult:
    """Compute one composite (``"L"`` or ``"R"``) in [-2, +2], renormalizing over live components."""
    components = [
        _component(
            s,
            as_of=as_of,
            root=root,
            globalcb_weights=globalcb_weights or {},
            staleness_budgets=staleness_budgets or {},
        )
        for s in specs
    ]
    live = [c for c in components if not c.dropped and c.x is not None and math.isfinite(c.x)]
    total_w = sum(c.weight for c in live)
    value = sum(c.weight * c.x for c in live) / total_w if total_w > 0 else None

    warnings = [f"{c.key} dropped — {c.reason}" for c in components if c.dropped]
    if value is not None and total_w < 0.999:
        warnings.append(
            f"{name}: renormalized over {total_w:.0%} of weight "
            f"({len(live)}/{len(components)} components live)"
        )
    return CompositeResult(name=name, value=value, components=components, warnings=warnings)
