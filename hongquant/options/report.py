"""Render OpEx risk reports for email and Telegram."""
from __future__ import annotations

from datetime import date

import numpy as np

from .types import Event, RiskScore, SnapshotBundle

_BAND_EMOJI = {"Low": "🟢", "Medium": "🟡", "High": "🟠", "Extreme": "🔴"}
_POSTURE = {
    "Low": "No action required. Normal volatility -- continue monitoring.",
    "Medium": "Avoid new high-beta additions. Watch QQQ/SPY divergence and SMH.",
    "High": "Consider reducing 20-40% of highest-beta / highest-gain momentum exposure. "
             "Prioritize: largest gainers, semiconductor names, stocks below 10d/20d line.",
    "Extreme": "Do not chase. Actively reduce crowded momentum exposure. "
               "No new high-beta adds until IV crush / dealer positioning clears.",
}


def render_email(
    score: RiskScore,
    bundles: list[SnapshotBundle],
    events: list[Event],
    *,
    today: date,
    vix_current: float = float("nan"),
    vix_5d_change: float = float("nan"),
    qqq_spy_rs: float = float("nan"),
    smh_qqq_rs: float = float("nan"),
    pct_above_20dma: float = float("nan"),
) -> tuple[str, str]:
    """Return (subject, markdown_body) for the weekly OpEx email report."""
    bundles[0] if bundles else None
    subject = _build_subject(score, bundles, today)
    body = _build_body(score, bundles, events, today=today, vix_current=vix_current,
                       vix_5d_change=vix_5d_change, qqq_spy_rs=qqq_spy_rs,
                       smh_qqq_rs=smh_qqq_rs, pct_above_20dma=pct_above_20dma)
    return subject, body


def render_telegram(
    score: RiskScore,
    bundles: list[SnapshotBundle],
    *,
    today: date,
) -> str:
    """Return a short Telegram pulse message."""
    primary = next((b for b in bundles if b.underlier == "QQQ"), bundles[0] if bundles else None)
    parts = [f"*[OpEx Risk: {score.band}]* {today}"]
    parts.append(f"Score: {score.total}/100")

    if primary:
        if not np.isnan(primary.front_iv_premium):
            parts.append(f"QQQ front IV premium: {primary.front_iv_premium:+.0%}")
        if primary.oi_vs_baseline is not None:
            parts.append(f"Friday OI: {primary.oi_vs_baseline:.1f}x avg")

    if score.reasons:
        top = score.reasons[:2]
        parts.append("Signals: " + " | ".join(top))

    parts.append(_POSTURE[score.band])
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pct(v: float, decimals: int = 1) -> str:
    if np.isnan(v):
        return "n/a"
    return f"{v:+.{decimals}%}"


def _f(v: float, decimals: int = 2) -> str:
    if np.isnan(v):
        return "n/a"
    return f"{v:.{decimals}f}"


def _build_subject(score: RiskScore, bundles: list[SnapshotBundle], today: date) -> str:
    qqq = next((b for b in bundles if b.underlier == "QQQ"), None)
    iv_part = f"front IV {_pct(qqq.front_iv_premium)}" if qqq else ""
    oi_part = (f"OI {qqq.oi_vs_baseline:.1f}xavg" if qqq and qqq.oi_vs_baseline else "")
    flags = ", ".join(p for p in [iv_part, oi_part] if p)
    return f"[OpEx Risk: {score.band}] {flags} -- {today}"


def _build_body(
    score: RiskScore,
    bundles: list[SnapshotBundle],
    events: list[Event],
    *,
    today: date,
    vix_current: float,
    vix_5d_change: float,
    qqq_spy_rs: float,
    smh_qqq_rs: float,
    pct_above_20dma: float,
) -> str:
    lines: list[str] = []

    # Header
    lines += [
        f"# OpEx Risk Report -- {today}",
        "",
        f"## Risk Level: {score.band} ({score.total}/100)",
        "",
        _POSTURE[score.band],
        "",
    ]

    # Triggered signals
    if score.reasons:
        lines += ["## Triggered Signals", ""]
        for r in score.reasons:
            lines.append(f"- {r}")
        lines.append("")

    # IV term structure table
    lines += ["## IV Term Structure", ""]
    lines.append("| Underlier | Front ATM IV | Next ATM IV | Front Premium | IV Rank |")
    lines.append("| --- | --- | --- | --- | --- |")
    for b in bundles:
        rank = f"{b.iv_rank:.0f}" if b.iv_rank is not None else "n/a"
        lines.append(
            f"| {b.underlier} | {_pct(b.front_atm_iv, 1)} | {_pct(b.next_atm_iv, 1)} "
            f"| **{_pct(b.front_iv_premium, 1)}** | {rank} |"
        )
    lines.append("")

    # OI / gamma concentration table
    lines += ["## OI / Gamma Concentration", ""]
    lines.append("| Underlier | Spot | Call OI | Put OI | PCR | Vol/OI | OI vs Avg | Call Wall | Put Wall | Max Pain |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for b in bundles:
        baseline = f"{b.oi_vs_baseline:.1f}x" if b.oi_vs_baseline is not None else "n/a"
        lines.append(
            f"| {b.underlier} | {_f(b.spot, 2)} "
            f"| {b.total_call_oi:,} | {b.total_put_oi:,} "
            f"| {_f(b.put_call_oi_ratio, 2)} | {_f(b.volume_oi_ratio, 2)} "
            f"| {baseline} | {_f(b.call_wall, 2)} | {_f(b.put_wall, 2)} | {_f(b.max_pain, 2)} |"
        )
    lines.append("")

    # Momentum fragility table
    lines += ["## Momentum Fragility", ""]
    lines.append("| Metric | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| QQQ / SPY 5d relative return | {_pct(qqq_spy_rs)} |")
    lines.append(f"| SMH / QQQ 5d relative return | {_pct(smh_qqq_rs)} |")
    lines.append(f"| % Watchlist above 20dma | {_pct(pct_above_20dma)} |")
    lines.append(f"| VIX current | {_f(vix_current, 1)} |")
    lines.append(f"| VIX 5d change | {_pct(vix_5d_change)} |")
    lines.append("")

    # Event calendar
    lines += ["## Event Calendar This Week", ""]
    if events:
        lines.append("| Date | Event | Importance |")
        lines.append("| --- | --- | --- |")
        for e in events:
            lines.append(f"| {e.date} | {e.label} | {e.importance} |")
    else:
        lines.append("No major scheduled events this week.")
    lines.append("")

    # Component scores
    lines += ["## Risk Score Breakdown", ""]
    lines.append("| Component | Score (0-1) | Max Points |")
    lines.append("| --- | --- | --- |")
    weight_map = {
        "iv_term_structure": 25, "oi_gamma_concentration": 25, "intraday_flow": 15,
        "momentum_weakness": 20, "event_calendar": 10, "vix_regime": 5,
    }
    for k, v in score.components.items():
        pts = weight_map.get(k, 0)
        lines.append(f"| {k.replace('_', ' ').title()} | {v:.2f} | {pts} |")
    lines.append("")

    # Risk posture
    lines += ["## Suggested Risk Posture", "", _POSTURE[score.band], ""]

    # Top 3 watch points for next session
    lines += ["## Top 3 to Watch Next Session", ""]
    watch = _build_watch_list(score, bundles)
    for i, w in enumerate(watch[:3], 1):
        lines.append(f"{i}. {w}")
    lines.append("")
    lines.append("---")
    lines.append("*Generated by HongQuant OpEx Risk Agent*")

    return "\n".join(lines)


def _build_watch_list(score: RiskScore, bundles: list[SnapshotBundle]) -> list[str]:
    items: list[str] = []
    qqq = next((b for b in bundles if b.underlier == "QQQ"), None)
    spy = next((b for b in bundles if b.underlier == "SPY"), None)

    if qqq and not np.isnan(qqq.call_wall):
        items.append(
            f"QQQ call wall at {qqq.call_wall:.2f} -- if price stalls here, "
            "resistance is meaningful; watch for volume rejection."
        )
    if qqq and not np.isnan(qqq.put_wall):
        items.append(
            f"QQQ put wall at {qqq.put_wall:.2f} -- break below may accelerate; "
            "monitor if QQQ dips to this level."
        )
    if qqq and not np.isnan(qqq.front_iv_premium) and qqq.front_iv_premium > 0.20:
        items.append(
            f"QQQ front IV premium {qqq.front_iv_premium:+.0%}: "
            "if IV stays elevated into Thursday, Friday vol risk remains high."
        )
    if spy and spy.oi_vs_baseline and spy.oi_vs_baseline >= 1.5:
        items.append(
            f"SPY Friday OI {spy.oi_vs_baseline:.1f}x average: "
            "large expiring position -- watch for pinning / price cluster near max pain."
        )
    if not items:
        items = [
            "Monitor QQQ/SPY relative strength -- divergence is the early warning.",
            "Watch front-week ATM IV vs next-week for any backwardation developing.",
            "Check SMH vs QQQ -- semiconductor leadership is a key momentum signal.",
        ]
    return items
