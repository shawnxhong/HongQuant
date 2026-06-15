"""Shared dataclasses for the Liquidity Regime Monitor."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Literal

Quadrant = Literal["Q1", "Q2", "Q3", "Q4"]
Direction = Literal["up", "down"]

# Quadrant labels (spec §4.3).
QUADRANT_LABELS: dict[Quadrant, str] = {
    "Q1": "顺风 (tailwind)",
    "Q2": "托底回撤 (backstopped pullback)",
    "Q3": "余热 (running on fumes)",
    "Q4": "双杀 (double kill)",
}


@dataclass
class IndicatorSpec:
    """One composite component, loaded from configs/lrm/indicators.yaml."""

    key: str
    label: str
    source: str               # fred | derived | globalcb | defillama | ipo_rel | stubs
    series: str               # FRED id, derived expression, or token
    op: str                   # delta | pct_change | level
    periods: int
    sign: int                 # +1 / -1 (positive = expansion / risk-on)
    weight: float
    frequency: str            # daily | weekly | monthly | quarterly
    enabled: bool = True
    proxy: bool = False        # using a degraded proxy source (e.g. DGS2-EFFR)

    def z_window(self) -> tuple[int, int]:
        """(window, min_periods) for the 5y rolling z-score, by frequency."""
        return {
            "daily": (1260, 756),     # 5y / 3y in trading days
            "weekly": (260, 156),
            "monthly": (60, 36),
            "quarterly": (20, 12),
        }.get(self.frequency, (1260, 756))


@dataclass
class ComponentValue:
    """A single component's contribution to a composite on one as-of date."""

    key: str
    label: str
    weight: float
    x: float | None = None        # clipped, signed z in [-2, +2]; None if unavailable
    dropped: bool = False
    reason: str | None = None     # why dropped (stale / no-data / disabled / proxy)


@dataclass
class CompositeResult:
    """L or R composite for one as-of date (spec §4.1)."""

    name: str                     # "L" or "R"
    value: float | None           # weighted, renormalized score in [-2, +2]
    components: list[ComponentValue] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def dropped(self) -> list[ComponentValue]:
        return [c for c in self.components if c.dropped]


@dataclass
class WaterLevel:
    """Position-water-level directive for a quadrant (spec §4.3)."""

    sleeve_max_pct: float
    leverage_max: float
    fragility_mult: float


@dataclass
class RegimeState:
    """The mechanical state-machine output for one monthly run (spec §4.2-4.3)."""

    asof: date
    quadrant: Quadrant
    provisional: bool
    l_score: float | None
    r_score: float | None
    l_direction: Direction
    r_direction: Direction
    water_level: WaterLevel
    notes: list[str] = field(default_factory=list)


@dataclass
class Alert:
    """One daily interrupt-rule evaluation (spec §6)."""

    rule_id: int
    name: str
    level: str
    fired: bool
    message: str
    triggers_downgrade: bool = False
