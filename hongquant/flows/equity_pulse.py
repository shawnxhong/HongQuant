"""Equity Pulse -- post-close daily flow.

Scans the universe of US equities/ETFs already in the OHLCV lake, computes
simple trend / momentum / extremes signals, and sends a Telegram pulse with
top movers, momentum leaders, 52w-high breakouts, drawdown alerts, and
universe breadth.

Run manually:
    uv run python -m hongquant.flows.equity_pulse --dry-run
    uv run python -m hongquant.flows.equity_pulse --dry-run --symbols SPY,QQQ,NVDA
"""
from __future__ import annotations

import argparse
from datetime import UTC, date, datetime, timedelta

import numpy as np
import pandas as pd
from prefect import flow, task

from ..data import store
from ..factors import equity as f
from ..logging import logger, setup_logging
from ..notify import notify
from ..universe import load_universe

TRAIL_PEAK_DAYS = 126
WIN_52W_DAYS = 252
NEAR_HIGH_PCT = 0.02
DRAWDOWN_ALERT = 0.15
TOP_N = 5
LOOKBACK_DAYS = 320  # > 252 trading days to fully populate 52w window


# ---------------------------------------------------------------------------
# Tasks
# ---------------------------------------------------------------------------

@task
def load_history(symbols: list[str], *, lookback_days: int = LOOKBACK_DAYS) -> pd.DataFrame:
    setup_logging()
    if not symbols:
        return pd.DataFrame()
    start = (datetime.now(tz=UTC) - timedelta(days=lookback_days)).date().isoformat()
    try:
        df = store.query_ohlcv(symbols, interval="1d", market="us", start=start)
    except Exception as exc:
        # DuckDB raises IOException when the parquet glob matches zero files
        # (e.g. cold-start before daily_equities has ever populated the lake).
        logger.warning("equity_pulse: OHLCV query failed -- {}", exc)
        return pd.DataFrame()
    logger.info("equity_pulse: loaded {} rows for {} symbols", len(df), len(symbols))
    return df


@task
def compute_snapshot(history: pd.DataFrame) -> pd.DataFrame:
    setup_logging()
    if history.empty:
        return pd.DataFrame()

    # Pivot to wide close prices: index=date, columns=symbol
    wide = (
        history.pivot_table(index="ts", columns="symbol", values="close", aggfunc="last")
        .sort_index()
    )

    rows: list[dict] = []
    for symbol in wide.columns:
        close = wide[symbol].dropna()
        if len(close) < 2:
            continue
        latest = float(close.iloc[-1])
        rows.append(
            {
                "symbol": symbol,
                "close": latest,
                "ret_1d": _last(f.pct_return(close, 1)),
                "ret_5d": _last(f.pct_return(close, 5)),
                "ret_20d": _last(f.pct_return(close, 20)),
                "ret_60d": _last(f.pct_return(close, 60)),
                "dist_50dma": _last(f.distance_from_sma(close, 50)),
                "dist_200dma": _last(f.distance_from_sma(close, 200)),
                "dist_52w_high": _last(f.distance_from_high(close, WIN_52W_DAYS)),
                "drawdown_6m": _last(f.drawdown_from_peak(close, TRAIL_PEAK_DAYS)),
                "rsi_14": _last(f.rsi(close, 14)),
            }
        )
    return pd.DataFrame(rows)


@task
def render_pulse(snapshot: pd.DataFrame, *, today: date) -> str:
    setup_logging()
    if snapshot.empty:
        return f"*Equity Pulse -- {today.isoformat()}*\nNo data."

    sections: list[str] = []

    # Header with breadth
    above_50 = _breadth(snapshot["dist_50dma"], threshold=0.0)
    above_200 = _breadth(snapshot["dist_200dma"], threshold=0.0)
    med_20d = snapshot["ret_20d"].median(skipna=True)
    header = (
        f"*Equity Pulse -- {today.isoformat()}*\n"
        f"Scanned {len(snapshot)}"
        + (f" | Above 50dma {above_50:.0f}%" if not np.isnan(above_50) else "")
        + (f" | Above 200dma {above_200:.0f}%" if not np.isnan(above_200) else "")
        + (f" | Median 20d {_signed(med_20d)}" if pd.notna(med_20d) else "")
    )
    sections.append(header)

    # Top movers (1d)
    movers = _format_movers(snapshot, "ret_1d", "Top movers (1d)")
    if movers:
        sections.append(movers)

    # Momentum leaders/laggards (20d)
    momentum = _format_movers(snapshot, "ret_20d", "Momentum leaders (20d)")
    if momentum:
        sections.append(momentum)

    # Near 52w high (within NEAR_HIGH_PCT)
    near_high = snapshot[
        snapshot["dist_52w_high"].notna() & (snapshot["dist_52w_high"] >= -NEAR_HIGH_PCT)
    ]
    if not near_high.empty:
        tickers = ", ".join(sorted(near_high["symbol"].tolist()))
        sections.append(f"*Near 52w high (within {int(NEAR_HIGH_PCT * 100)}%)*\n{tickers}")

    # Drawdown alerts
    dd = snapshot[
        snapshot["drawdown_6m"].notna() & (snapshot["drawdown_6m"] <= -DRAWDOWN_ALERT)
    ].sort_values("drawdown_6m")
    if not dd.empty:
        items = ", ".join(
            f"{r.symbol} {r.drawdown_6m * 100:+.0f}%" for r in dd.itertuples(index=False)
        )
        sections.append(
            f"*Drawdown alerts (>={int(DRAWDOWN_ALERT * 100)}% from 6m peak)*\n{items}"
        )

    return "\n\n".join(sections)


@task
def deliver(text: str, *, channels: list[str], dry_run: bool = False) -> None:
    setup_logging()
    if dry_run:
        logger.info("DRY RUN -- equity pulse:\n{}", text)
        return
    if "telegram" in channels:
        notify(text)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _last(series: pd.Series) -> float:
    if series.empty:
        return float("nan")
    value = series.iloc[-1]
    try:
        fval = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return fval if np.isfinite(fval) else float("nan")


def _breadth(series: pd.Series, *, threshold: float) -> float:
    """Percentage of finite values strictly greater than threshold."""
    s = series.dropna()
    if s.empty:
        return float("nan")
    return float((s > threshold).mean() * 100.0)


def _signed(x: float) -> str:
    return f"{x * 100:+.1f}%"


def _format_movers(snapshot: pd.DataFrame, col: str, title: str) -> str:
    s = snapshot[["symbol", col]].dropna(subset=[col])
    if s.empty:
        return ""
    up = s.nlargest(TOP_N, col)
    down = s.nsmallest(TOP_N, col)
    up_str = "  ".join(f"{r.symbol} {_signed(getattr(r, col))}" for r in up.itertuples(index=False))
    down_str = "  ".join(
        f"{r.symbol} {_signed(getattr(r, col))}" for r in down.itertuples(index=False)
    )
    return f"*{title}*\n+ {up_str}\n- {down_str}"


# ---------------------------------------------------------------------------
# Flow
# ---------------------------------------------------------------------------

@flow(name="equity_pulse")
def equity_pulse(
    *,
    dry_run: bool = False,
    symbols: list[str] | None = None,
    universe_path: str = "configs/universe.yaml",
) -> None:
    setup_logging()
    if symbols is None:
        universe = load_universe(universe_path)
        symbols = sorted(set(
            universe.us_sector_etfs
            + universe.us_broad_etfs
            + universe.us_factor_etfs
            + universe.us_stocks_watchlist
            + universe.momentum_watchlist
        ))
    if not symbols:
        logger.warning("equity_pulse: empty universe, nothing to do")
        return

    logger.info("equity_pulse: {} symbols", len(symbols))
    history = load_history(symbols)
    if history.empty:
        msg = (
            "*Equity Pulse:* no OHLCV history found in the local lake. "
            "Run `uv run python -m hongquant.flows.daily_equities --symbols "
            f"{','.join(symbols[:5])}{'...' if len(symbols) > 5 else ''}` first."
        )
        if dry_run:
            logger.info("DRY RUN -- {}", msg)
        else:
            notify(msg)
        return

    snapshot = compute_snapshot(history)
    today = date.today()
    text = render_pulse(snapshot, today=today)
    deliver(text, channels=["telegram"], dry_run=dry_run)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Equity Pulse daily flow")
    p.add_argument("--dry-run", action="store_true", help="Print pulse instead of sending")
    p.add_argument(
        "--symbols",
        default=None,
        help="Comma-separated symbol override (skips universe loading)",
    )
    return p.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    syms = (
        [t.strip().upper() for t in args.symbols.split(",") if t.strip()]
        if args.symbols
        else None
    )
    equity_pulse(dry_run=args.dry_run, symbols=syms)
