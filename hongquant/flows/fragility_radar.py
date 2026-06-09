"""Trend Flash-Crash Radar — Prefect flow.

Daily post-close fragility scan over the themed clusters in configs/universe.yaml
(gold complex, AI semis, megacap tech, Korea). Per instrument it outputs a 0-100
conditional-fragility score (Extension x Crowding x Fragility, gated by a
market-level systemic multiplier), a cross-sectional rank, a day-over-day delta,
a tiered position/hedge posture with a falsification companion, and — for flagged
names — a Bull's-Advocate vs Fragility-Hawk LLM briefing.

Telegram gets a daily digest; Email fires only on a state change (band crossing
or rapid deterioration). Scores persist to a Parquet store that seeds the live
calibration ledger.

Run manually:
    uv run python -m hongquant.flows.fragility_radar --dry-run --no-llm
    uv run python -m hongquant.flows.fragility_radar --dry-run --clusters ai_semis
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

import pandas as pd
from prefect import flow, task

from ..data import store as price_store
from ..data.adapters import cot as cot_adapter
from ..data.adapters import yfinance_ as yfa
from ..email import send_email
from ..llm.agents import fragility_redteam
from ..logging import logger, setup_logging
from ..notify import notify
from ..options.events import EventCalendar
from ..options.expiries import front_friday, next_friday
from ..universe import Universe, load_universe

# ---------------------------------------------------------------------------
# Fetch tasks (each degrades to empty / None on failure — never raises)
# ---------------------------------------------------------------------------

@task(retries=2, retry_delay_seconds=20)
def fetch_prices(symbols: list[str], *, lookback_days: int = 800) -> dict[str, pd.Series]:
    setup_logging()
    if not symbols:
        return {}
    start = (datetime.now(tz=UTC) - timedelta(days=lookback_days)).date().isoformat()
    try:
        df = yfa.fetch_ohlcv(symbols, start=start, interval="1d")
    except Exception as exc:
        logger.warning("price fetch failed: {}", exc)
        return {}
    if df.empty:
        return {}
    try:
        price_store.write_ohlcv(df)  # best-effort lake hygiene
    except Exception as exc:
        logger.debug("price persist skipped: {}", exc)

    out: dict[str, pd.Series] = {}
    for sym, chunk in df.groupby("symbol"):
        s = chunk.set_index("ts")["close"].sort_index()
        s.index = pd.to_datetime(s.index).date
        out[str(sym)] = s
    logger.info("fragility: prices for {}/{} symbols", len(out), len(symbols))
    return out


@task
def fetch_chains(symbols: list[str]) -> dict[str, dict]:
    setup_logging()
    from ..options.adapters import yfinance_options as yfo

    today = date.today()
    targets = [front_friday(today), next_friday(today)]
    out: dict[str, dict] = {}
    for sym in symbols:
        try:
            chain = yfo.fetch_chain_snapshot(sym, expirations=targets)
        except Exception as exc:
            logger.debug("{}: chain fetch failed — {}", sym, exc)
            continue
        if chain is None or chain.empty:
            continue
        spot_vals = chain["spot"].dropna()
        spot = float(spot_vals.iloc[-1]) if not spot_vals.empty else None
        exps = pd.to_datetime(chain["expiration"]).dt.date
        front = front_friday(today) if front_friday(today) in set(exps) else min(exps)
        out[sym] = {"chain": chain, "spot": spot, "front_expiry": front}
    logger.info("fragility: option chains for {}/{} symbols", len(out), len(symbols))
    return out


@task
def fetch_vol_structure() -> dict:
    setup_logging()
    import yfinance as yf

    out: dict = {"vix": None, "vix3m": None, "vix9d": None,
                 "vvix_series": None, "skew_series": None}
    tickers = {"vix": "^VIX", "vix3m": "^VIX3M", "vix9d": "^VIX9D",
               "vvix": "^VVIX", "skew": "^SKEW"}
    try:
        data = yf.download(list(tickers.values()), period="3y", progress=False, auto_adjust=True)
        closes = data["Close"] if isinstance(data.columns, pd.MultiIndex) else data
    except Exception as exc:
        logger.warning("vol structure fetch failed: {}", exc)
        return out

    for key, sym in tickers.items():
        try:
            s = closes[sym].dropna()
        except Exception:
            continue
        if s.empty:
            continue
        if key in ("vix", "vix3m", "vix9d"):
            out[key] = float(s.iloc[-1])
        else:
            out[f"{key}_series"] = s
    return out


@task
def fetch_cot() -> dict[str, pd.Series]:
    setup_logging()
    out: dict[str, pd.Series] = {}
    for market in ("GOLD", "SILVER"):
        try:
            s = cot_adapter.managed_money_net(market)
        except Exception as exc:
            logger.debug("COT {} failed — {}", market, exc)
            continue
        if not s.empty:
            out[market] = s
    return out


# ---------------------------------------------------------------------------
# Pure scoring core (no I/O — directly unit-testable)
# ---------------------------------------------------------------------------

# COMEX COT market a watchlist symbol maps to (others have no clean COT series).
_COT_MAP = {"GLD": "GOLD", "SLV": "SILVER"}


def _build_scores(
    universe: Universe,
    *,
    prices: dict[str, pd.Series],
    chains: dict[str, dict],
    cot: dict[str, pd.Series],
    market_scores: dict[str, float | None],
    gate,
    today: date,
):
    from ..fragility import crowding, extension
    from ..fragility import fragility_pillar as cpillar
    from ..fragility import score as scoremod
    from ..fragility.cluster import cluster_signal
    from ..fragility.types import InstrumentFeatures

    # Cluster correlation percentile (shared by every member of a cluster).
    cluster_pctile: dict[str, float | None] = {}
    for members in universe.fragility_clusters.values():
        closes = {s: prices[s] for s in members if s in prices}
        _, pctile = cluster_signal(closes)
        for s in members:
            cluster_pctile[s] = pctile

    scores = []
    for sym in universe.fragility_symbols:
        closes = prices.get(sym)
        if closes is None or len(closes.dropna()) < 60:
            logger.debug("{}: insufficient price history; skipping", sym)
            continue
        ch = chains.get(sym, {})
        cot_net = cot.get(_COT_MAP[sym]) if sym in _COT_MAP else None
        feat = InstrumentFeatures(
            symbol=sym,
            asof=today,
            cluster=universe.cluster_of(sym),
            closes=closes,
            spot=ch.get("spot"),
            chain=ch.get("chain"),
            front_expiry=ch.get("front_expiry"),
            cot_net=cot_net,
            cluster_corr_pctile=cluster_pctile.get(sym),
        )
        pa = extension.compute(closes)
        pb = crowding.compute(feat)
        pc = cpillar.compute(feat, market_scores)
        scores.append(
            scoremod.compute_fragility(
                sym, today, pillar_a=pa, pillar_b=pb, pillar_c=pc,
                gate=gate, cluster=feat.cluster,
            )
        )

    scoremod.rank_and_flag(scores)
    return scores


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

def _deliver(subject: str, email_body: str, tg_body: str, *, channels: list[str],
             dry_run: bool) -> None:
    setup_logging()
    if dry_run:
        logger.info("DRY RUN — subject: {}", subject)
        logger.info("DRY RUN — telegram:\n{}", tg_body)
        logger.info("DRY RUN — email (first 1500 chars):\n{}", email_body[:1500])
        return
    if "telegram" in channels:
        notify(tg_body)
    if "email" in channels:
        send_email(subject, email_body)


def _run(
    *,
    dry_run: bool,
    clusters: list[str] | None,
    symbols: list[str] | None,
    use_llm: bool,
    universe_path: str,
) -> None:
    from ..fragility import report
    from ..fragility import score as scoremod
    from ..fragility import store as fstore
    from ..fragility.fragility_pillar import market_vol_scores
    from ..fragility.systemic import compute_systemic_gate
    from ..fragility.types import BAND_ORDER

    universe = load_universe(universe_path)
    # Narrow the universe to requested clusters / symbols if asked.
    if clusters:
        universe.fragility_clusters = {
            k: v for k, v in universe.fragility_clusters.items() if k in clusters
        }
    if symbols:
        universe.fragility_clusters = {
            k: [s for s in v if s in symbols] for k, v in universe.fragility_clusters.items()
        }
    syms = universe.fragility_symbols
    if not syms:
        logger.warning("fragility: empty universe, nothing to do")
        return
    today = date.today()
    logger.info("fragility radar: {} symbols across {} clusters",
                len(syms), len(universe.fragility_clusters))

    prices = fetch_prices(syms)
    chains = fetch_chains(syms)
    vol = fetch_vol_structure()
    cot = fetch_cot()

    market_scores = market_vol_scores(
        vix=vol.get("vix"), vix3m=vol.get("vix3m"), vix9d=vol.get("vix9d"),
        vvix_series=vol.get("vvix_series"), skew_series=vol.get("skew_series"),
    )
    gate = compute_systemic_gate(vix=vol.get("vix"), vix3m=vol.get("vix3m"), vix9d=vol.get("vix9d"))

    scores = _build_scores(
        universe, prices=prices, chains=chains, cot=cot,
        market_scores=market_scores, gate=gate, today=today,
    )
    if not scores:
        msg = (f"Fragility Radar {today}: no instruments scored — check data sources "
               f"(price/options/COT/FRED access).")
        if dry_run:
            logger.warning("DRY RUN — {}", msg)
        else:
            notify(msg)
        return

    # Change detection vs the persisted history.
    prior = fstore.prior_bands(today)
    for s in scores:
        scoremod.attach_deltas(s, fstore.read_history(s.symbol, before=today))
    state_changed = [s for s in scores if scoremod.is_state_change(s, prior.get(s.symbol))]
    flagged = [s for s in scores if BAND_ORDER[s.band] >= BAND_ORDER["Alert"]] or state_changed

    events = EventCalendar(momentum_watchlist=syms).events_this_week(today)

    narrative = None
    if use_llm and flagged:
        narrative = fragility_redteam.brief(flagged, events=events, gate=gate, today=today)

    subject, email_body = report.render_email(scores, gate, events, today=today, narrative=narrative)
    tg_body = report.render_telegram(scores, today=today, narrative=narrative)

    channels = ["telegram"] + (["email"] if state_changed else [])
    logger.info("fragility radar: {} scored, {} flagged, {} state-changes -> channels {}",
                len(scores), len(flagged), len(state_changed), channels)
    _deliver(subject, email_body, tg_body, channels=channels, dry_run=dry_run)

    if not dry_run:
        fstore.write_scores(scores, asof=today)


@flow(name="fragility_radar")
def fragility_radar(
    *,
    dry_run: bool = False,
    clusters: list[str] | None = None,
    symbols: list[str] | None = None,
    use_llm: bool = True,
    universe_path: str = "configs/universe.yaml",
) -> None:
    setup_logging()
    _run(dry_run=dry_run, clusters=clusters, symbols=symbols,
         use_llm=use_llm, universe_path=universe_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Trend Flash-Crash Radar")
    p.add_argument("--dry-run", action="store_true", help="Print report instead of sending")
    p.add_argument("--no-llm", action="store_true", help="Skip the LLM red-team narrative")
    p.add_argument("--clusters", default=None, help="Comma-separated cluster subset, e.g. ai_semis,gold_complex")
    p.add_argument("--symbols", default=None, help="Comma-separated symbol subset")
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    cl = [c.strip() for c in args.clusters.split(",")] if args.clusters else None
    sy = [s.strip().upper() for s in args.symbols.split(",")] if args.symbols else None
    fragility_radar(dry_run=args.dry_run, clusters=cl, symbols=sy, use_llm=not args.no_llm)
