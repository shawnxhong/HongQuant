"""State-card JSON — the cross-system contract (spec §7.2).

Written to ``data/state/lrm_state_card.json`` (latest) plus an archived copy per
run. The fragility system reads ``quadrant`` and
``water_level.fragility_alert_multiplier``; the (future) vol system reads
``quadrant`` for context. Carries ``l_direction``/``r_direction`` and the L/R
scores so next month's state machine can resolve hysteresis.
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ..config import get_settings
from ..logging import logger
from .types import Alert, CompositeResult, RegimeState

VERSION = "1.0"


def _state_dir(root: Path | None) -> Path:
    return (root or get_settings().data_dir) / "state"


def run_id_for(asof: date) -> str:
    return f"lrm-{asof:%Y-%m}"


def _vintage_summary(results: list[CompositeResult]) -> dict[str, str]:
    """Per-component status (live / dropped reason / proxy) for the card + report appendix."""
    out: dict[str, str] = {}
    for res in results:
        for c in res.components:
            out[c.key] = c.reason or "live"
    return out


def build_state_card(
    *,
    regime: RegimeState,
    l_result: CompositeResult,
    r_result: CompositeResult,
    alerts: list[Alert],
    reaction_function: dict[str, Any] | None = None,
    analyst_dissent: str | None = None,
) -> dict[str, Any]:
    """Assemble the §7.2 state-card dict from a monthly run."""
    wl = regime.water_level
    return {
        "system": "LRM",
        "version": VERSION,
        "as_of": regime.asof.isoformat(),
        "run_id": run_id_for(regime.asof),
        "quadrant": regime.quadrant,
        "quadrant_provisional": regime.provisional,
        "L_score": round(regime.l_score, 4) if regime.l_score is not None else None,
        "R_score": round(regime.r_score, 4) if regime.r_score is not None else None,
        "l_direction": regime.l_direction,
        "r_direction": regime.r_direction,
        "water_level": {
            "active_sleeve_max_pct": wl.sleeve_max_pct,
            "leverage_max": wl.leverage_max,
            "fragility_alert_multiplier": wl.fragility_mult,
        },
        "reaction_function": reaction_function,
        "alerts_active": [a.name for a in alerts if a.fired],
        "data_vintages": _vintage_summary([l_result, r_result]),
        "analyst_dissent": analyst_dissent,
    }


def write_state_card(card: dict[str, Any], *, root: Path | None = None) -> Path:
    """Write the latest card + an archived per-run copy. Returns the latest path."""
    state_dir = _state_dir(root)
    (state_dir / "lrm").mkdir(parents=True, exist_ok=True)
    latest = state_dir / "lrm_state_card.json"
    archive = state_dir / "lrm" / f"{card['run_id']}.json"
    payload = json.dumps(card, ensure_ascii=False, indent=2)
    latest.write_text(payload, encoding="utf-8")
    archive.write_text(payload, encoding="utf-8")
    logger.info("LRM state card written: {} (quadrant {})", latest, card["quadrant"])
    return latest


def read_latest(*, root: Path | None = None) -> dict[str, Any] | None:
    """Read the latest state card (the prior month's, used for hysteresis); None if absent."""
    latest = _state_dir(root) / "lrm_state_card.json"
    if not latest.exists():
        return None
    try:
        return json.loads(latest.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("could not read prior state card: {}", exc)
        return None
