"""Monthly report + alert digest rendering (spec §7.1).

Renders Markdown (the shared email._md_to_html turns it into HTML). The report
is complete WITHOUT the LLM — the optional synthesis is appended only when the
advisory layer is enabled.
"""
from __future__ import annotations

from datetime import date
from typing import Any

from .types import QUADRANT_LABELS, Alert, CompositeResult, RegimeState


def _fmt(x: float | None, places: int = 2) -> str:
    return "n/a" if x is None else f"{x:+.{places}f}"


def _component_rows(result: CompositeResult) -> list[str]:
    rows = []
    for c in result.components:
        status = "dropped" if c.dropped else "live"
        if c.reason and not c.dropped:
            status = c.reason
        x = "—" if c.x is None else f"{c.x:+.2f}"
        rows.append(f"| {c.key} | {c.label} | {c.weight:.2f} | {x} | {status} |")
    return rows


def _composite_panel(title: str, result: CompositeResult) -> list[str]:
    out = [f"## {title}: {_fmt(result.value)}", "", "| key | indicator | weight | x (signed z) | status |", "|---|---|---|---|---|"]
    out += _component_rows(result)
    out.append("")
    return out


def render_monthly(
    regime: RegimeState,
    l_result: CompositeResult,
    r_result: CompositeResult,
    alerts: list[Alert],
    *,
    today: date,
    synthesis: str | None = None,
    reaction_function: dict[str, Any] | None = None,
) -> tuple[str, str]:
    """Return ``(subject, markdown_body)`` for the monthly report."""
    quad = regime.quadrant
    label = QUADRANT_LABELS.get(quad, quad)
    wl = regime.water_level
    subject = f"LRM {today:%Y-%m} — {quad} {label} (sleeve ≤{wl.sleeve_max_pct:.0f}%)"

    fired = [a for a in alerts if a.fired]
    rf_status = (reaction_function or {}).get("status") or "n/a"
    gap = (reaction_function or {}).get("fed_vs_market_gap_bps")

    lines = [
        f"# Liquidity Regime Monitor — {today:%Y-%m}",
        "",
        "## Status card",
        f"- **Quadrant: {quad} — {label}**" + ("  _(provisional)_" if regime.provisional else ""),
        f"- L score {_fmt(regime.l_score)} ({regime.l_direction}) · R score {_fmt(regime.r_score)} ({regime.r_direction})",
        f"- Water level: active sleeve **≤ {wl.sleeve_max_pct:.0f}%**, leverage ≤ {wl.leverage_max:.1f}x, "
        f"fragility multiplier x{wl.fragility_mult:.1f}",
        f"- Reaction function: {rf_status}" + (f" · fed-vs-market gap {gap:+.0f}bp" if gap is not None else ""),
        f"- Interrupts fired this run: {', '.join(a.name for a in fired) if fired else 'none'}",
    ]
    for note in regime.notes:
        lines.append(f"- _{note}_")
    lines.append("")

    lines += _composite_panel("L composite (liquidity / price of money)", l_result)
    lines += _composite_panel("R composite (private risk-taking)", r_result)

    if fired:
        lines += ["## Active interrupts", ""]
        for a in fired:
            tag = " — **downgrade suggested**" if a.triggers_downgrade else ""
            lines.append(f"- [{a.level}] {a.name}: {a.message}{tag}")
        lines.append("")

    if synthesis:
        lines += ["## Analyst synthesis (advisory)", "", synthesis, ""]

    warnings = l_result.warnings + r_result.warnings
    lines += ["## Appendix — data quality", ""]
    if warnings:
        lines += [f"- {w}" for w in warnings]
    else:
        lines.append("- all components live; no renormalization")
    lines += [
        "",
        "_LRM is a regime conditioner: it sizes risk, it does not pick trades. "
        "Thresholds are pre-committed priors with no evidence status until the shadow run completes (spec §10)._",
    ]
    return subject, "\n".join(lines)


def render_monthly_telegram(regime: RegimeState, alerts: list[Alert], *, today: date) -> str:
    quad = regime.quadrant
    wl = regime.water_level
    fired = [a.name for a in alerts if a.fired]
    head = f"*[LRM {today:%Y-%m}]* {quad} {QUADRANT_LABELS.get(quad, quad)}"
    if regime.provisional:
        head += " (provisional)"
    body = [
        head,
        f"L {_fmt(regime.l_score)} ({regime.l_direction}) · R {_fmt(regime.r_score)} ({regime.r_direction})",
        f"Sleeve ≤{wl.sleeve_max_pct:.0f}% · lev ≤{wl.leverage_max:.1f}x · frag x{wl.fragility_mult:.1f}",
    ]
    if fired:
        body.append("Interrupts: " + ", ".join(fired))
    return "\n".join(body)


def render_alert_digest(
    alerts: list[Alert],
    *,
    today: date,
    downgrade_suggestion: str | None = None,
) -> str:
    """Telegram body for the daily interrupt run; empty string if nothing fired."""
    fired = [a for a in alerts if a.fired]
    if not fired:
        return ""
    lines = [f"*[LRM interrupts {today:%Y-%m-%d}]*"]
    for a in fired:
        mark = "🔴" if a.triggers_downgrade else "🟡"
        lines.append(f"{mark} [{a.level}] {a.name}: {a.message}")
    if downgrade_suggestion:
        lines.append(f"\n⚠️ Provisional downgrade suggested → {downgrade_suggestion} (requires human confirmation)")
    return "\n".join(lines)
