"""Pure metric functions over an options chain DataFrame. No I/O."""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd


def atm_iv(chain: pd.DataFrame, expiry: date, spot: float) -> float:
    """ATM implied volatility for a given expiry, averaged across calls and puts."""
    if chain.empty or "expiration" not in chain.columns:
        return float("nan")
    sub = chain[chain["expiration"] == expiry].copy()
    if sub.empty:
        return float("nan")
    sub["dist"] = (sub["strike"] - spot).abs()
    ivs: list[float] = []
    for opt_type in ("call", "put"):
        rows = sub[sub["option_type"] == opt_type]
        if rows.empty:
            continue
        row = rows.loc[rows["dist"].idxmin()]
        iv = row["implied_volatility"]
        if pd.notna(iv) and iv > 0:
            ivs.append(float(iv))
    return float(np.mean(ivs)) if ivs else float("nan")


def iv_term_structure(chain: pd.DataFrame, spot: float) -> dict[date, float]:
    """ATM IV per expiration date, sorted ascending."""
    result: dict[date, float] = {}
    for expiry in sorted(chain["expiration"].unique()):
        iv = atm_iv(chain, expiry, spot)
        if not np.isnan(iv):
            result[expiry] = iv
    return result


def front_iv_premium(chain: pd.DataFrame, spot: float, front_expiry: date, next_expiry: date) -> float:
    """Fractional IV premium of front expiry over next expiry. Positive = backwardation."""
    f_iv = atm_iv(chain, front_expiry, spot)
    n_iv = atm_iv(chain, next_expiry, spot)
    if np.isnan(f_iv) or np.isnan(n_iv) or n_iv == 0:
        return float("nan")
    return f_iv / n_iv - 1.0


def total_oi(chain: pd.DataFrame, expiry: date) -> dict[str, int | float]:
    """Aggregate OI for a given expiry by type."""
    sub = chain[chain["expiration"] == expiry]
    call_oi = int(sub[sub["option_type"] == "call"]["open_interest"].sum())
    put_oi = int(sub[sub["option_type"] == "put"]["open_interest"].sum())
    total = call_oi + put_oi
    return {
        "call": call_oi,
        "put": put_oi,
        "total": total,
        "put_call_ratio": (put_oi / call_oi) if call_oi > 0 else float("nan"),
    }


def near_atm_oi(chain: pd.DataFrame, expiry: date, spot: float, *, pct: float = 0.02) -> int:
    """Total OI within ±pct of spot for a given expiry."""
    sub = chain[chain["expiration"] == expiry]
    lo, hi = spot * (1 - pct), spot * (1 + pct)
    return int(sub[(sub["strike"] >= lo) & (sub["strike"] <= hi)]["open_interest"].sum())


def volume_oi_ratio(chain: pd.DataFrame, expiry: date) -> float:
    """Ratio of total volume to total OI for a given expiry (intraday activity indicator)."""
    sub = chain[chain["expiration"] == expiry]
    total_vol = sub["volume"].sum()
    total_open = sub["open_interest"].sum()
    if total_open == 0:
        return float("nan")
    return float(total_vol / total_open)


def gamma_exposure_by_strike(chain: pd.DataFrame, expiry: date, spot: float) -> pd.DataFrame:
    """Gamma exposure per strike. Formula: OI x 100 x gamma x spot^2 x 0.01.

    This approximates the dollar delta change for a 1% spot move.
    Returns a DataFrame with columns: strike, call_gex, put_gex, net_gex.
    """
    sub = chain[chain["expiration"] == expiry].copy()
    if sub.empty:
        return pd.DataFrame(columns=["strike", "call_gex", "put_gex", "net_gex"])

    multiplier = 100.0 * (spot ** 2) * 0.01
    sub["gex"] = sub["open_interest"] * sub["gamma"].fillna(0) * multiplier

    calls = sub[sub["option_type"] == "call"].groupby("strike")["gex"].sum().rename("call_gex")
    puts = sub[sub["option_type"] == "put"].groupby("strike")["gex"].sum().rename("put_gex")

    result = pd.concat([calls, puts], axis=1).fillna(0).reset_index()
    result["net_gex"] = result["call_gex"] - result["put_gex"]
    return result.sort_values("strike").reset_index(drop=True)


def call_wall(chain: pd.DataFrame, expiry: date, spot: float) -> float:
    """Strike above spot with the highest call OI (resistance level)."""
    sub = chain[(chain["expiration"] == expiry) & (chain["option_type"] == "call") & (chain["strike"] > spot)]
    if sub.empty:
        return float("nan")
    return float(sub.loc[sub["open_interest"].idxmax(), "strike"])


def put_wall(chain: pd.DataFrame, expiry: date, spot: float) -> float:
    """Strike below spot with the highest put OI (support / acceleration level)."""
    sub = chain[(chain["expiration"] == expiry) & (chain["option_type"] == "put") & (chain["strike"] < spot)]
    if sub.empty:
        return float("nan")
    return float(sub.loc[sub["open_interest"].idxmax(), "strike"])


def max_pain(chain: pd.DataFrame, expiry: date) -> float:
    """Strike that minimizes total payout to option holders (max pain theory)."""
    sub = chain[chain["expiration"] == expiry]
    if sub.empty:
        return float("nan")

    calls = sub[sub["option_type"] == "call"][["strike", "open_interest"]]
    puts = sub[sub["option_type"] == "put"][["strike", "open_interest"]]
    candidate_strikes = sorted(sub["strike"].unique())

    min_pain = float("inf")
    pain_strike = candidate_strikes[0]
    for k in candidate_strikes:
        call_pain = (
            calls[calls["strike"] < k]["open_interest"] * (k - calls[calls["strike"] < k]["strike"])
        ).sum()
        put_pain = (
            puts[puts["strike"] > k]["open_interest"] * (puts[puts["strike"] > k]["strike"] - k)
        ).sum()
        total = float(call_pain + put_pain)
        if total < min_pain:
            min_pain = total
            pain_strike = k
    return float(pain_strike)


def expected_move(chain: pd.DataFrame, expiry: date, spot: float) -> float:
    """Expected move as a fraction of spot, estimated from the ATM straddle price."""
    sub = chain[chain["expiration"] == expiry].copy()
    if sub.empty or spot <= 0:
        return float("nan")
    sub["dist"] = (sub["strike"] - spot).abs()
    atm_strike = float(sub.loc[sub["dist"].idxmin(), "strike"])

    call_mid = sub[(sub["option_type"] == "call") & (sub["strike"] == atm_strike)]
    put_mid = sub[(sub["option_type"] == "put") & (sub["strike"] == atm_strike)]
    if call_mid.empty or put_mid.empty:
        return float("nan")

    c_row = call_mid.iloc[0]
    p_row = put_mid.iloc[0]
    c_price = (c_row["bid"] + c_row["ask"]) / 2 if c_row["ask"] > 0 else c_row["last"]
    p_price = (p_row["bid"] + p_row["ask"]) / 2 if p_row["ask"] > 0 else p_row["last"]
    straddle = float(c_price + p_price)
    return straddle / spot if spot > 0 else float("nan")


def oi_vs_baseline(today_total_oi: int, history: pd.Series[float]) -> float | None:
    """Ratio of today's OI to 12-week trailing mean. Returns None if < 4 data points."""
    if history is None or len(history) < 4:
        return None
    mean = float(history.mean())
    if mean <= 0:
        return None
    return today_total_oi / mean


def iv_rank(current_iv: float, history: pd.Series[float]) -> float | None:
    """IV rank: percentile of current_iv within the trailing history (0-100).

    Returns None if < 4 data points.
    """
    if history is None or len(history) < 4:
        return None
    lo, hi = float(history.min()), float(history.max())
    if hi <= lo:
        return 50.0
    return float(np.clip((current_iv - lo) / (hi - lo) * 100, 0, 100))
