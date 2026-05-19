"""OpEx Momentum Risk Agent — Prefect flow.

Schedule (America/New_York):
  pulse:  08:00, 11:30, 15:30 Mon-Tue-Thu  → Telegram only
  weekly: Wed 15:30 + Fri 10:30            → Email + Telegram

Run manually:
  uv run python -m hongquant.flows.opex_risk --mode pulse
  uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime
from typing import Literal

import pandas as pd
from prefect import flow, task

from ..config import get_settings
from ..email import send_email
from ..logging import logger, setup_logging
from ..notify import notify
from ..options import metrics as m
from ..options import store as opt_store
from ..options.events import EventCalendar
from ..options.expiries import front_friday, next_friday
from ..options.momentum import breadth, momentum_fragility_score, relative_strength
from ..options.report import render_email, render_telegram
from ..options.risk_score import compute_risk_score
from ..options.types import SnapshotBundle
from ..universe import load_universe

# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task(retries=2, retry_delay_seconds=30)
def fetch_chain(underlier: str, *, provider: str) -> pd.DataFrame:
    setup_logging()
    if provider == "polygon":
        from ..options.adapters.polygon_options import fetch_chain_snapshot
    elif provider == "yfinance":
        from ..options.adapters.yfinance_options import fetch_chain_snapshot
    elif provider == "ibkr":
        from ..options.adapters.ibkr_options import fetch_chain_snapshot
    else:
        raise ValueError(f"Unsupported options data provider: {provider}")

    today = date.today()
    targets = [front_friday(today), next_friday(today)]
    df = fetch_chain_snapshot(underlier, expirations=targets)
    logger.info("{}: fetched {} contracts", underlier, len(df))
    return df


@task
def persist_snapshot(chain: pd.DataFrame) -> None:
    setup_logging()
    if chain.empty:
        return
    str(chain["underlier"].iloc[0])
    ts = chain["snapshot_ts"].iloc[0]
    snapshot_ts = ts if hasattr(ts, "tzinfo") else datetime.now(tz=UTC)
    opt_store.write_snapshot(chain, snapshot_ts=snapshot_ts)


@task
def build_bundle(chain: pd.DataFrame) -> SnapshotBundle | None:
    setup_logging()
    if chain.empty:
        return None

    underlier = str(chain["underlier"].iloc[0])
    today = date.today()
    front = front_friday(today)
    nxt = next_friday(today)

    spot_vals = chain["spot"].dropna()
    if spot_vals.empty:
        logger.warning("{}: no spot price in chain", underlier)
        return None
    spot = float(spot_vals.iloc[-1])

    front_iv = m.atm_iv(chain, front, spot)
    next_iv = m.atm_iv(chain, nxt, spot)
    prem = m.front_iv_premium(chain, spot, front, nxt)
    oi_data = m.total_oi(chain, front)
    voi = m.volume_oi_ratio(chain, front)
    near_oi = m.near_atm_oi(chain, front, spot)
    cwall = m.call_wall(chain, front, spot)
    pwall = m.put_wall(chain, front, spot)
    mpain = m.max_pain(chain, front)
    emove = m.expected_move(chain, front, spot)
    gex_df = m.gamma_exposure_by_strike(chain, front, spot)

    # Historical context (None if insufficient data)
    iv_hist = opt_store.historical_atm_iv(underlier)
    iv_r = m.iv_rank(front_iv, iv_hist) if len(iv_hist) >= 4 else None

    oi_hist = opt_store.historical_friday_oi(underlier)
    oi_baseline = m.oi_vs_baseline(oi_data["total"], oi_hist) if len(oi_hist) >= 4 else None

    return SnapshotBundle(
        underlier=underlier,
        spot=spot,
        snapshot_ts=datetime.now(tz=UTC),
        chain=chain,
        front_expiry=front,
        next_expiry=nxt,
        front_atm_iv=front_iv,
        next_atm_iv=next_iv,
        front_iv_premium=prem,
        iv_rank=iv_r,
        total_call_oi=int(oi_data["call"]),
        total_put_oi=int(oi_data["put"]),
        put_call_oi_ratio=float(oi_data["put_call_ratio"]),
        volume_oi_ratio=voi,
        near_atm_oi=near_oi,
        call_wall=cwall,
        put_wall=pwall,
        max_pain=mpain,
        expected_move=emove,
        gamma_by_strike=gex_df,
        oi_vs_baseline=oi_baseline,
    )


@task
def fetch_momentum_signals(momentum_watchlist: list[str]) -> dict:
    setup_logging()
    try:
        qqq_spy = relative_strength("QQQ", "SPY", window=5)
        smh_qqq = relative_strength("SMH", "QQQ", window=5)
        b = breadth(momentum_watchlist, window_short=20, window_long=50)
    except Exception as exc:
        logger.warning("Momentum fetch failed: {}", exc)
        return {"qqq_spy_rs": float("nan"), "smh_qqq_rs": float("nan"),
                "pct_above_20dma": float("nan"), "pct_above_50dma": float("nan"),
                "advancers_5d": 0, "decliners_5d": 0}
    return {"qqq_spy_rs": qqq_spy, "smh_qqq_rs": smh_qqq, **b}


@task
def fetch_vix() -> dict:
    setup_logging()
    try:
        import yfinance as yf

        vix = yf.download("^VIX", period="10d", progress=False, auto_adjust=True)
        if isinstance(vix.columns, pd.MultiIndex):
            closes = vix["Close"]["^VIX"]
        elif "Close" in vix.columns:
            closes = vix["Close"]
        else:
            return {"vix_current": float("nan"), "vix_5d_change": float("nan")}
        closes = closes.dropna()
        if len(closes) < 2:
            return {"vix_current": float(closes.iloc[-1]) if len(closes) else float("nan"),
                    "vix_5d_change": float("nan")}
        current = float(closes.iloc[-1])
        start = float(closes.iloc[0])
        change = (current / start - 1) if start > 0 else float("nan")
        return {"vix_current": current, "vix_5d_change": change}
    except Exception as exc:
        logger.warning("VIX fetch failed: {}", exc)
        return {"vix_current": float("nan"), "vix_5d_change": float("nan")}


@task
def deliver(
    subject: str,
    email_body: str,
    tg_body: str,
    *,
    channels: list[str],
    dry_run: bool = False,
) -> None:
    setup_logging()
    if dry_run:
        logger.info("DRY RUN — subject: {}", subject)
        logger.info("DRY RUN — email body (first 500 chars):\n{}", email_body[:500])
        logger.info("DRY RUN — telegram body:\n{}", tg_body)
        return
    if "email" in channels:
        send_email(subject, email_body)
    if "telegram" in channels:
        notify(tg_body)


# ---------------------------------------------------------------------------
# Flows
# ---------------------------------------------------------------------------

def _run_scan(
    *,
    channels: list[str],
    dry_run: bool = False,
    mode: Literal["pulse", "weekly"] = "pulse",
    provider: str | None = None,
    underliers: list[str] | None = None,
) -> None:
    universe = load_universe("configs/universe.yaml")
    momentum_watchlist = universe.momentum_watchlist
    today = date.today()
    provider = (provider or get_settings().options_data_provider).lower()
    if underliers is not None:
        core_tickers = underliers
    elif provider == "yfinance":
        # Yahoo is good enough for ETF-option dev runs, but unreliable for SPX/NDX index chains.
        core_tickers = universe.options_underliers.get("core_etfs", universe.options_core_tickers)
    else:
        core_tickers = universe.options_core_tickers  # SPY, QQQ, SMH, SOXX, SPX, NDX
    logger.info("OpEx options data provider: {}", provider)
    logger.info("OpEx underliers: {}", ", ".join(core_tickers))

    # Fetch chains (sequential to respect Polygon rate limits; parallelise if on paid plan)
    chains: list[pd.DataFrame] = []
    for ticker in core_tickers:
        try:
            chain = fetch_chain(ticker, provider=provider)
            persist_snapshot(chain)
            chains.append(chain)
        except Exception as exc:
            logger.exception("{}: chain fetch failed — {}", ticker, exc)

    # Build bundles
    bundles = [b for c in chains if (b := build_bundle(c)) is not None]

    if not bundles:
        msg = (
            f"OpEx Risk Agent: no bundles built for {today} "
            f"using {provider} — check data-source access, rate limits, and requested underliers."
        )
        if dry_run:
            logger.warning("DRY RUN — {}", msg)
        else:
            notify(msg)
        return

    # Momentum + VIX signals
    mom = fetch_momentum_signals(momentum_watchlist)
    vix = fetch_vix()

    mom_fragility = momentum_fragility_score(
        qqq_spy_rs=mom.get("qqq_spy_rs", float("nan")),
        smh_qqq_rs=mom.get("smh_qqq_rs", float("nan")),
        pct_above_20dma=mom.get("pct_above_20dma", float("nan")),
        vix_5d_change=vix.get("vix_5d_change", float("nan")),
    )

    # Event calendar
    cal = EventCalendar(momentum_watchlist=momentum_watchlist)
    events = cal.events_this_week(today)

    # Score
    score = compute_risk_score(
        bundles,
        vix_current=vix.get("vix_current", float("nan")),
        vix_5d_change=vix.get("vix_5d_change", float("nan")),
        momentum_fragility=mom_fragility,
        events=events,
        today=today,
    )
    logger.info("OpEx Risk Score: {}/100 ({})", score.total, score.band)

    # Render
    subject, email_body = render_email(
        score, bundles, events,
        today=today,
        vix_current=vix.get("vix_current", float("nan")),
        vix_5d_change=vix.get("vix_5d_change", float("nan")),
        qqq_spy_rs=mom.get("qqq_spy_rs", float("nan")),
        smh_qqq_rs=mom.get("smh_qqq_rs", float("nan")),
        pct_above_20dma=mom.get("pct_above_20dma", float("nan")),
    )
    tg_body = render_telegram(score, bundles, today=today)

    deliver(subject, email_body, tg_body, channels=channels, dry_run=dry_run)


@flow(name="opex_risk_pulse")
def opex_risk_pulse(
    *,
    dry_run: bool = False,
    provider: str | None = None,
    underliers: list[str] | None = None,
) -> None:
    """Light daily scan (08:00, 11:30, 15:30 ET). Delivers to Telegram only."""
    setup_logging()
    _run_scan(
        channels=["telegram"],
        dry_run=dry_run,
        mode="pulse",
        provider=provider,
        underliers=underliers,
    )


@flow(name="opex_risk_weekly")
def opex_risk_weekly(
    *,
    dry_run: bool = False,
    provider: str | None = None,
    underliers: list[str] | None = None,
) -> None:
    """Full weekly report (Wed 15:30 ET, Fri 10:30 ET). Delivers to Email + Telegram."""
    setup_logging()
    _run_scan(
        channels=["email", "telegram"],
        dry_run=dry_run,
        mode="weekly",
        provider=provider,
        underliers=underliers,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="OpEx Momentum Risk Agent")
    p.add_argument("--mode", choices=["pulse", "weekly"], default="weekly")
    p.add_argument("--dry-run", action="store_true", help="Print report instead of sending")
    p.add_argument(
        "--provider",
        choices=["yfinance", "polygon", "ibkr"],
        default=None,
        help="Options data provider; defaults to OPTIONS_DATA_PROVIDER or yfinance",
    )
    p.add_argument(
        "--underliers",
        default=None,
        help="Comma-separated underlier override for smoke tests, e.g. SPY or SPY,QQQ",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    underliers = (
        [ticker.strip().upper() for ticker in args.underliers.split(",") if ticker.strip()]
        if args.underliers
        else None
    )
    if args.mode == "pulse":
        opex_risk_pulse(dry_run=args.dry_run, provider=args.provider, underliers=underliers)
    else:
        opex_risk_weekly(dry_run=args.dry_run, provider=args.provider, underliers=underliers)
