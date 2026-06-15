"""Load configs/lrm/*.yaml into typed structures (mirrors universe.py)."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..logging import logger
from .types import IndicatorSpec

NETLIQ_WEIGHT_CAP = 0.20  # spec §1.3 — NetLiq weight is hard-capped


@dataclass
class SeriesCatalogEntry:
    id: str
    source: str
    frequency: str
    ticker: str | None = None
    enabled: bool = True


@dataclass
class IndicatorConfig:
    series_catalog: list[SeriesCatalogEntry] = field(default_factory=list)
    l_composite: list[IndicatorSpec] = field(default_factory=list)
    r_composite: list[IndicatorSpec] = field(default_factory=list)
    globalcb_weights: dict[str, float] = field(default_factory=dict)


@dataclass
class ThresholdConfig:
    state_machine: dict[str, Any] = field(default_factory=dict)
    water_levels: dict[str, dict[str, float]] = field(default_factory=dict)
    plumbing: dict[str, float] = field(default_factory=dict)
    staleness_budget_days: dict[str, int] = field(default_factory=dict)
    alerts: list[dict[str, Any]] = field(default_factory=list)


def _spec(d: dict[str, Any]) -> IndicatorSpec:
    return IndicatorSpec(
        key=d["key"],
        label=d["label"],
        source=d["source"],
        series=str(d["series"]),
        op=d["op"],
        periods=int(d["periods"]),
        sign=int(d["sign"]),
        weight=float(d["weight"]),
        frequency=d["frequency"],
        enabled=bool(d.get("enabled", True)),
        proxy=bool(d.get("proxy", False)),
    )


def _enforce_netliq_cap(specs: list[IndicatorSpec]) -> None:
    for s in specs:
        if s.key == "net_liquidity" and s.weight > NETLIQ_WEIGHT_CAP:
            logger.warning(
                "NetLiq weight {} exceeds cap {}; clamping (spec §1.3)",
                s.weight,
                NETLIQ_WEIGHT_CAP,
            )
            s.weight = NETLIQ_WEIGHT_CAP


def load_indicators(path: Path | str = "configs/lrm/indicators.yaml") -> IndicatorConfig:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    catalog = [
        SeriesCatalogEntry(
            id=e["id"],
            source=e["source"],
            frequency=e["frequency"],
            ticker=e.get("ticker"),
            enabled=bool(e.get("enabled", True)),
        )
        for e in data.get("series_catalog", [])
    ]
    l_specs = [_spec(d) for d in data.get("l_composite", [])]
    r_specs = [_spec(d) for d in data.get("r_composite", [])]
    _enforce_netliq_cap(l_specs)
    return IndicatorConfig(
        series_catalog=catalog,
        l_composite=l_specs,
        r_composite=r_specs,
        globalcb_weights={k: float(v) for k, v in data.get("globalcb_weights", {}).items()},
    )


def load_thresholds(path: Path | str = "configs/lrm/thresholds.yaml") -> ThresholdConfig:
    with open(path) as f:
        data = yaml.safe_load(f) or {}
    return ThresholdConfig(
        state_machine=data.get("state_machine", {}),
        water_levels=data.get("water_levels", {}),
        plumbing=data.get("plumbing", {}),
        staleness_budget_days=data.get("staleness_budget_days", {}),
        alerts=data.get("alerts", []),
    )


def load_dots(path: Path | str = "configs/lrm/dots.yaml") -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}
