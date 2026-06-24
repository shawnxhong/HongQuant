"""Liquidity Regime Monitor — Prefect flow (spec §2 run calendar).

Two modes share one entrypoint (mirrors opex_risk's --mode):
  monthly  — last Saturday of the month: ingest, composites, state machine,
             report, state card, optional LLM synthesis. Email + Telegram.
  daily    — 07:00 Beijing: ingest daily series, evaluate interrupts, notify.

Run manually:
  uv run python -m hongquant.flows.liquidity_monitor --mode monthly --dry-run --no-llm
  uv run python -m hongquant.flows.liquidity_monitor --mode daily --dry-run
"""
from __future__ import annotations

import argparse
import json
from datetime import date

from prefect import flow, task

from ..liquidity import alerts as alerts_mod
from ..liquidity import report as report_mod
from ..liquidity import statecard, store
from ..liquidity.composites import compute_composite
from ..liquidity.config_load import load_dots, load_indicators, load_thresholds
from ..liquidity.ingest import ingest_catalog
from ..liquidity.llm import runner as llm_runner
from ..liquidity.regime import compute_regime, suggest_downgrade
from ..logging import logger, setup_logging
from ..notify import notify, notify_email


@task(retries=2, retry_delay_seconds=30)
def ingest(catalog, *, as_of: date) -> dict[str, int]:
    setup_logging()
    return ingest_catalog(catalog, as_of=as_of)


def _reaction_function(as_of: date) -> dict:
    """Mechanical fed-vs-market gap (bp): 2Y yield minus next-year dot median."""
    dots = load_dots().get("median_dots", {})
    median = dots.get(as_of.year + 1) or dots.get(str(as_of.year + 1))
    dgs2 = store.read_series_asof("DGS2", as_of=as_of).dropna()
    gap = None
    if not dgs2.empty and median is not None:
        gap = round((float(dgs2.iloc[-1]) - float(median)) * 100)
    return {"status": None, "dominant_variable": None, "fed_vs_market_gap_bps": gap}


def _run_monthly(*, dry_run: bool, use_llm: bool) -> None:
    today = date.today()
    ind = load_indicators()
    thr = load_thresholds()

    try:
        ingest(ind.series_catalog, as_of=today)
    except Exception as exc:
        logger.warning("ingest failed ({}); scoring from existing store", exc)

    l_result = compute_composite(
        "L", ind.l_composite, as_of=today,
        globalcb_weights=ind.globalcb_weights, staleness_budgets=thr.staleness_budget_days,
    )
    r_result = compute_composite(
        "R", ind.r_composite, as_of=today,
        globalcb_weights=ind.globalcb_weights, staleness_budgets=thr.staleness_budget_days,
    )
    logger.info("L={} R={}", l_result.value, r_result.value)

    prior = statecard.read_latest()
    regime = compute_regime(
        asof=today,
        l_score=l_result.value,
        r_score=r_result.value,
        prior=prior,
        state_machine=thr.state_machine,
        water_levels=thr.water_levels,
    )
    reaction = _reaction_function(today)

    alerts = alerts_mod.evaluate_alerts(thr.alerts, as_of=today)

    synthesis = None
    if use_llm and llm_runner.is_enabled():
        payload = json.dumps(
            {
                "quadrant": regime.quadrant,
                "L": l_result.value,
                "R": r_result.value,
                "components": {c.key: c.x for c in (*l_result.components, *r_result.components)},
                "alerts_fired": [a.name for a in alerts if a.fired],
                "prior": prior,
            },
            ensure_ascii=False, default=str,
        )
        synthesis = llm_runner.run_text_task(llm_runner.load_prompt("p4_synthesis"), payload)

    subject, body = report_mod.render_monthly(
        regime, l_result, r_result, alerts, today=today,
        synthesis=synthesis, reaction_function=reaction,
    )
    tg = report_mod.render_monthly_telegram(regime, alerts, today=today)

    card = statecard.build_state_card(
        regime=regime, l_result=l_result, r_result=r_result,
        alerts=alerts, reaction_function=reaction,
    )

    if dry_run:
        logger.info("DRY RUN — subject: {}", subject)
        logger.info("DRY RUN — report:\n{}", body)
        logger.info("DRY RUN — state card:\n{}", json.dumps(card, ensure_ascii=False, indent=2))
        return
    statecard.write_state_card(card)
    notify_email(subject, body)
    notify(tg)


def _run_daily(*, dry_run: bool) -> None:
    today = date.today()
    ind = load_indicators()
    thr = load_thresholds()

    try:
        ingest(ind.series_catalog, as_of=today)
    except Exception as exc:
        logger.warning("ingest failed ({}); evaluating alerts on existing store", exc)

    alerts = alerts_mod.evaluate_alerts(thr.alerts, as_of=today)
    fired = [a for a in alerts if a.fired]

    downgrade = None
    if any(a.triggers_downgrade for a in fired):
        prior = statecard.read_latest()
        if prior and prior.get("quadrant"):
            downgrade = suggest_downgrade(prior["quadrant"])

    digest = report_mod.render_alert_digest(alerts, today=today, downgrade_suggestion=downgrade)
    logger.info("daily interrupts: {} fired", len(fired))

    if not digest:
        logger.info("no interrupts fired; nothing to send")
        return
    if dry_run:
        logger.info("DRY RUN — alert digest:\n{}", digest)
        return
    notify(digest)


@flow(name="liquidity_monitor_monthly")
def liquidity_monitor_monthly(*, dry_run: bool = False, use_llm: bool = True) -> None:
    setup_logging()
    _run_monthly(dry_run=dry_run, use_llm=use_llm)


@flow(name="liquidity_monitor_daily")
def liquidity_monitor_daily(*, dry_run: bool = False) -> None:
    setup_logging()
    _run_daily(dry_run=dry_run)


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Liquidity Regime Monitor")
    p.add_argument("--mode", choices=["monthly", "daily"], default="monthly")
    p.add_argument("--dry-run", action="store_true", help="Print instead of sending/persisting")
    p.add_argument("--no-llm", action="store_true", help="Skip the advisory LLM synthesis")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.mode == "monthly":
        liquidity_monitor_monthly(dry_run=args.dry_run, use_llm=not args.no_llm)
    else:
        liquidity_monitor_daily(dry_run=args.dry_run)
