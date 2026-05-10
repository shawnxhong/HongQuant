"""Shared dataclasses for the options risk agent."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

import pandas as pd


@dataclass
class Event:
    date: date
    kind: str  # FOMC | CPI | NFP | EARNINGS | MONTHLY_OPEX | TRIPLE_WITCHING
    label: str
    importance: Literal["LOW", "MEDIUM", "HIGH"]


@dataclass
class SnapshotBundle:
    underlier: str
    spot: float
    snapshot_ts: datetime                   # UTC
    chain: pd.DataFrame                     # one row per contract
    front_expiry: date
    next_expiry: date
    front_atm_iv: float                     # e.g. 0.32 = 32%
    next_atm_iv: float
    front_iv_premium: float                 # fraction: front/next - 1
    iv_rank: float | None                   # 0-100 scale; None if < 4 weeks of history
    total_call_oi: int
    total_put_oi: int
    put_call_oi_ratio: float
    volume_oi_ratio: float
    near_atm_oi: int                        # OI within ±2% of spot
    call_wall: float                        # strike with max call OI above spot
    put_wall: float                         # strike with max put OI below spot
    max_pain: float
    expected_move: float                    # ATM straddle price / spot (fraction)
    gamma_by_strike: pd.DataFrame           # columns: strike, call_gex, put_gex, net_gex
    oi_vs_baseline: float | None            # ratio vs 12-week avg; None if insufficient history


@dataclass
class RiskScore:
    total: int                              # 0-100
    band: Literal["Low", "Medium", "High", "Extreme"]
    components: dict[str, float]            # component_name -> normalized 0-1 score
    reasons: list[str] = field(default_factory=list)
