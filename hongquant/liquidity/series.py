"""Resolve an indicator spec to a point-in-time pandas Series.

Bridges the vintage store and the composites: reads raw series as-of the run
date, applies the fill policy, and builds the derived series (NetLiq, AUD/JPY,
CCC-BB, the implied-path proxy, the global-CB blend, the IPO/SPY ratio).
Stub/disabled sources return an empty Series so the composite drops them.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pandas as pd

from . import quality, store
from .types import IndicatorSpec

_STUB_SOURCES = {"akshare_cn", "finra", "mof_jp", "nyfed"}
_GLOBALCB_GROWTH_PERIODS = 13  # ~3 months at weekly cadence


def resolve_series(
    spec: IndicatorSpec,
    *,
    as_of: date,
    root: Path | None = None,
    globalcb_weights: dict[str, float] | None = None,
) -> pd.Series:
    """Return the raw (pre-transform) series for a component, or empty if unavailable."""
    if not spec.enabled or spec.source in _STUB_SOURCES:
        return pd.Series(dtype="float64")

    def read(sid: str) -> pd.Series:
        return store.read_series_asof(sid, as_of=as_of, root=root)

    if spec.source in ("fred", "defillama"):
        return quality.forward_fill(read(spec.series), spec.frequency)
    if spec.source == "derived":
        return _derived(spec.series, read)
    if spec.source == "globalcb":
        return _globalcb(spec.series, read, globalcb_weights or {})
    if spec.source == "ipo_rel":
        return _ratio(spec.series, read)
    return pd.Series(dtype="float64")


def _tokens(expr: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9_^]+|[+\-*]", expr.replace(" ", ""))


def _aligned_frame(ids: list[str], read) -> pd.DataFrame | None:
    raw = {i: read(i) for i in ids}
    if any(s.empty for s in raw.values()):
        return None
    # Outer-join on the union of dates, then forward-fill so a daily leg lines up
    # with a weekly one. Frequency is reimposed by reindexing to the primary leg.
    return pd.DataFrame(raw).sort_index().ffill()


def _derived(expr: str, read) -> pd.Series:
    """Evaluate a left-to-right +/-/* expression of FRED ids (no mixed precedence)."""
    toks = _tokens(expr)
    ids = [t for t in toks if re.match(r"[A-Za-z]", t)]
    df = _aligned_frame(ids, read)
    if df is None:
        return pd.Series(dtype="float64")
    primary_id = toks[0]
    result = df[primary_id].copy()
    i = 1
    while i < len(toks):
        op, rid = toks[i], toks[i + 1]
        rhs = df[rid]
        if op == "+":
            result = result + rhs
        elif op == "-":
            result = result - rhs
        elif op == "*":
            result = result * rhs
        i += 2
    # Reimpose the primary leg's cadence (e.g. weekly for NetLiq -> Δ13w = 13 weeks).
    primary_dates = read(primary_id).index
    return result.reindex(primary_dates).dropna()


def _globalcb(expr: str, read, weights: dict[str, float]) -> pd.Series:
    """USD-size-weighted blend of each CB's local-currency ~3m balance-sheet growth."""
    ids = [i.strip() for i in expr.split(",")]
    present = {i: read(i) for i in ids}
    present = {i: s for i, s in present.items() if not s.empty}
    if not present:
        return pd.Series(dtype="float64")
    df = pd.DataFrame(present).sort_index().ffill()
    total_w = sum(weights.get(i, 0.0) for i in present) or 1.0
    blend = sum(
        df[i].pct_change(_GLOBALCB_GROWTH_PERIODS) * (weights.get(i, 0.0) / total_w)
        for i in present
    )
    return blend.dropna()


def _ratio(expr: str, read) -> pd.Series:
    """A numerator/denominator ratio series, e.g. IPO/SPY."""
    num_id, den_id = (s.strip() for s in expr.split("/"))
    df = _aligned_frame([num_id, den_id], read)
    if df is None:
        return pd.Series(dtype="float64")
    return (df[num_id] / df[den_id]).dropna()
