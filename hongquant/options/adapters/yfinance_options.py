"""yfinance options chain adapter for zero-cost development runs.

Yahoo's option chains include bid/ask, last, volume, open interest, and IV, but
not Greeks. We estimate Greeks locally from Black-Scholes so the downstream
OpEx risk pipeline can run before a paid options data feed is wired in.
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pandas as pd

from ...logging import logger, setup_logging
from .polygon_options import CHAIN_COLUMNS

UNDERLIER_MAP: dict[str, str] = {
    "SPX": "^SPX",
    "NDX": "^NDX",
    "VIX": "^VIX",
}

_RISK_FREE_RATE = 0.045


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _estimate_greeks(
    *,
    option_type: str,
    spot: float,
    strike: float,
    implied_volatility: float,
    expiration: date,
    as_of: date,
) -> tuple[float, float, float, float]:
    """Return delta, gamma, theta, vega using a simple Black-Scholes model."""
    if spot <= 0 or strike <= 0 or implied_volatility <= 0:
        return (float("nan"), float("nan"), float("nan"), float("nan"))

    days = max((expiration - as_of).days, 1)
    t = days / 365.0
    sigma = implied_volatility
    sqrt_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (_RISK_FREE_RATE + 0.5 * sigma * sigma) * t) / (
        sigma * sqrt_t
    )
    d2 = d1 - sigma * sqrt_t
    pdf = _norm_pdf(d1)

    if option_type == "call":
        delta = _norm_cdf(d1)
        theta = (
            -(spot * pdf * sigma) / (2 * sqrt_t)
            - _RISK_FREE_RATE * strike * math.exp(-_RISK_FREE_RATE * t) * _norm_cdf(d2)
        ) / 365.0
    else:
        delta = _norm_cdf(d1) - 1.0
        theta = (
            -(spot * pdf * sigma) / (2 * sqrt_t)
            + _RISK_FREE_RATE * strike * math.exp(-_RISK_FREE_RATE * t) * _norm_cdf(-d2)
        ) / 365.0

    gamma = pdf / (spot * sigma * sqrt_t)
    vega = spot * pdf * sqrt_t / 100.0
    return (float(delta), float(gamma), float(theta), float(vega))


def _spot_price(ticker: object) -> float:
    hist = ticker.history(period="5d", auto_adjust=True)
    if not hist.empty and "Close" in hist.columns:
        closes = hist["Close"].dropna()
        if not closes.empty:
            return float(closes.iloc[-1])

    fast_info = getattr(ticker, "fast_info", {}) or {}
    for key in ("last_price", "lastPrice", "regular_market_price"):
        try:
            value = fast_info[key]
        except Exception:
            continue
        if value:
            return float(value)

    return float("nan")


def _normalize_side(
    raw: pd.DataFrame,
    *,
    underlier: str,
    option_type: str,
    expiration: date,
    spot: float,
    snapshot_ts: datetime,
) -> list[dict]:
    if raw.empty:
        return []

    as_of = snapshot_ts.date()
    records: list[dict] = []
    for row in raw.to_dict("records"):
        strike = float(row.get("strike") or 0)
        iv = float(row.get("impliedVolatility") or float("nan"))
        delta, gamma, theta, vega = _estimate_greeks(
            option_type=option_type,
            spot=spot,
            strike=strike,
            implied_volatility=iv,
            expiration=expiration,
            as_of=as_of,
        )
        records.append(
            {
                "underlier": underlier,
                "expiration": expiration,
                "strike": strike,
                "option_type": option_type,
                "bid": float(row.get("bid") or 0),
                "ask": float(row.get("ask") or 0),
                "last": float(row.get("lastPrice") or 0),
                "volume": int(0 if pd.isna(row.get("volume")) else row.get("volume") or 0),
                "open_interest": int(
                    0 if pd.isna(row.get("openInterest")) else row.get("openInterest") or 0
                ),
                "implied_volatility": iv,
                "delta": delta,
                "gamma": gamma,
                "theta": theta,
                "vega": vega,
                "spot": spot,
                "snapshot_ts": snapshot_ts,
            }
        )
    return records


def fetch_chain_snapshot(
    underlier: str,
    *,
    expirations: list[date] | None = None,
) -> pd.DataFrame:
    """Fetch options chains from yfinance and normalize to CHAIN_COLUMNS.

    This adapter is intended for development and smoke tests. It should not be
    treated as a production-grade market data source.
    """
    setup_logging()
    import yfinance as yf

    yahoo_symbol = UNDERLIER_MAP.get(underlier, underlier)
    ticker = yf.Ticker(yahoo_symbol)
    available = {date.fromisoformat(exp) for exp in getattr(ticker, "options", [])}
    requested = expirations or sorted(available)
    targets = [exp for exp in requested if exp in available]

    if not targets:
        logger.warning(
            "{}: yfinance has no requested expirations; requested={}, available_sample={}",
            underlier,
            [exp.isoformat() for exp in requested],
            [exp.isoformat() for exp in sorted(available)[:5]],
        )
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    spot = _spot_price(ticker)
    snapshot_ts = datetime.now(tz=UTC)
    records: list[dict] = []

    for expiry in targets:
        chain = ticker.option_chain(expiry.isoformat())
        records.extend(
            _normalize_side(
                chain.calls,
                underlier=underlier,
                option_type="call",
                expiration=expiry,
                spot=spot,
                snapshot_ts=snapshot_ts,
            )
        )
        records.extend(
            _normalize_side(
                chain.puts,
                underlier=underlier,
                option_type="put",
                expiration=expiry,
                spot=spot,
                snapshot_ts=snapshot_ts,
            )
        )

    if not records:
        logger.warning("{}: yfinance returned 0 contracts", underlier)
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    df = pd.DataFrame(records)
    numeric_cols = [
        "strike",
        "bid",
        "ask",
        "last",
        "implied_volatility",
        "delta",
        "gamma",
        "theta",
        "vega",
        "spot",
    ]
    for col in numeric_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["volume"] = pd.to_numeric(df["volume"], errors="coerce").fillna(0).astype("int64")
    df["open_interest"] = (
        pd.to_numeric(df["open_interest"], errors="coerce").fillna(0).astype("int64")
    )

    logger.info("{}: {} contracts fetched from yfinance", underlier, len(df))
    return df[CHAIN_COLUMNS].reset_index(drop=True)


def fetch_previous_day_oi(underlier: str) -> pd.DataFrame:
    """Fetch current yfinance chain snapshot for OI population."""
    return fetch_chain_snapshot(underlier)
