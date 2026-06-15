"""Daily interrupt engine (spec §6) — rule-table driven from thresholds.yaml.

Each rule reads point-in-time series from the vintage store and evaluates a
single ``kind`` of trigger. bp thresholds assume the FRED series is in percent,
so raw changes are multiplied by 100. Red interrupts (``downgrade: true``) flag a
provisional one-step quadrant downgrade for human confirmation — they never auto
-apply it.
"""
from __future__ import annotations

from collections.abc import Callable
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd

from ..logging import logger
from . import store
from .types import Alert


def _accessor(as_of: date, root: Path | None) -> Callable[[str], pd.Series]:
    def get(series_id: str) -> pd.Series:
        return store.read_series_asof(series_id, as_of=as_of, root=root).dropna()

    return get


def _spread(get: Callable[[str], pd.Series], a: str, b: str) -> pd.Series:
    df = pd.DataFrame({"a": get(a), "b": get(b)}).dropna()
    return df["a"] - df["b"]  # in percent


def _audjpy(get: Callable[[str], pd.Series]) -> pd.Series:
    df = pd.DataFrame({"a": get("DEXUSAL"), "b": get("DEXJPUS")}).dropna()
    return df["a"] * df["b"]


def _pct_over(s: pd.Series, window: int) -> float | None:
    s = s.dropna()
    if len(s) <= window:
        return None
    return (s.iloc[-1] / s.iloc[-1 - window] - 1.0) * 100.0


def _evaluate_one(rule: dict[str, Any], get: Callable[[str], pd.Series]) -> tuple[bool, str]:
    kind = rule["kind"]

    if kind == "spread_streak":
        s = _spread(get, rule["a"], rule["b"]).dropna()
        tail = s.tail(rule["days"])
        fired = len(tail) >= rule["days"] and bool((tail > 0).all())
        last_bp = tail.iloc[-1] * 100 if len(tail) else float("nan")
        return fired, f"{rule['a']}-{rule['b']} positive {int((tail > 0).sum())}/{rule['days']}d (last {last_bp:+.1f}bp)"

    if kind == "spread_level_bp":
        s = _spread(get, rule["a"], rule["b"]).dropna()
        if s.empty:
            return False, "no data"
        last = s.iloc[-1] * 100
        return last >= rule["bp"], f"{rule['a']}-{rule['b']} = {last:+.1f}bp (≥{rule['bp']})"

    if kind == "zscore_jump":
        d = get(rule["series"]).dropna().diff().dropna()
        w = d.tail(rule["window"])
        sd = float(w.std(ddof=0))
        if len(w) < 10 or sd == 0:
            return False, "insufficient history"
        z = (float(d.iloc[-1]) - float(w.mean())) / sd
        return z >= rule["sigma"], f"{rule['series']} weekly chg z={z:.1f} (>={rule['sigma']} sd)"

    if kind == "change_bp":
        s = get(rule["series"]).dropna()
        if len(s) <= rule["window"]:
            return False, "insufficient history"
        chg = (s.iloc[-1] - s.iloc[-1 - rule["window"]]) * 100
        return chg >= rule["bp"], f"{rule['series']} {chg:+.0f}bp/{rule['window']}d (≥{rule['bp']})"

    if kind in ("pct_change_up", "pct_change_down", "abs_pct_change"):
        pct = _pct_over(get(rule["series"]), rule["window"])
        if pct is None:
            return False, "insufficient history"
        if kind == "pct_change_up":
            fired = pct >= rule["pct"]
        elif kind == "pct_change_down":
            fired = pct <= -rule["pct"]
        else:
            fired = abs(pct) >= rule["pct"]
        return fired, f"{rule['series']} {pct:+.1f}%/{rule['window']}d"

    if kind == "audjpy_ndx":
        aud_pct = _pct_over(_audjpy(get), rule["window"])
        ndx_pct = _pct_over(get("NDX"), rule["window"])
        if aud_pct is None or ndx_pct is None:
            return False, "insufficient history"
        fired = aud_pct <= rule["audjpy_pct"] and ndx_pct >= rule["ndx_min"]
        return fired, f"AUD/JPY {aud_pct:+.1f}% vs NDX {ndx_pct:+.1f}% /{rule['window']}d"

    return False, f"unknown rule kind {kind!r}"


def evaluate_alerts(rules: list[dict[str, Any]], *, as_of: date, root: Path | None = None) -> list[Alert]:
    """Evaluate every interrupt rule against the store as-of ``as_of``."""
    get = _accessor(as_of, root)
    alerts: list[Alert] = []
    for rule in rules:
        try:
            fired, message = _evaluate_one(rule, get)
        except Exception as exc:
            logger.warning("alert {} evaluation failed: {}", rule.get("name"), exc)
            fired, message = False, f"eval error: {exc}"
        alerts.append(
            Alert(
                rule_id=int(rule["id"]),
                name=rule["name"],
                level=rule["level"],
                fired=fired,
                message=message,
                triggers_downgrade=bool(rule.get("downgrade")) and fired,
            )
        )
    return alerts
