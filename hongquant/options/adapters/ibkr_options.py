"""Interactive Brokers options chain snapshot adapter.

Requires IB Gateway (recommended) or TWS to be running locally with API access
enabled and an OPRA market-data subscription on the account. Install the
optional dependency with ``uv sync --extra ibkr``.

The adapter opens one TCP connection per call, requests a chain snapshot via
``reqSecDefOptParams`` + ``reqTickers``, then disconnects. It is strictly
read-only -- no orders are placed.
"""
from __future__ import annotations

import math
from datetime import UTC, date, datetime

import pandas as pd

from ...config import get_settings
from ...logging import logger, setup_logging
from .polygon_options import CHAIN_COLUMNS

# symbol -> (secType, exchange) for non-stock underliers
UNDERLIER_EXCHANGE: dict[str, tuple[str, str]] = {
    "SPX": ("IND", "CBOE"),
    "NDX": ("IND", "NASDAQ"),
    "VIX": ("IND", "CBOE"),
}

# Filter strikes to a band around spot to keep request volume manageable.
_DEFAULT_STRIKE_BAND_PCT = 0.15
_CHUNK_SIZE = 50
_REQ_TIMEOUT = 15.0


def _import_ib_async():
    try:
        import ib_async  # type: ignore
    except ImportError as exc:
        raise RuntimeError(
            "ib_async is not installed. Run `uv sync --extra ibkr` to install it."
        ) from exc
    return ib_async


def _build_underlier_contract(ib_async_mod, underlier: str):
    if underlier in UNDERLIER_EXCHANGE:
        _sec_type, exchange = UNDERLIER_EXCHANGE[underlier]
        return ib_async_mod.Index(underlier, exchange, "USD")
    return ib_async_mod.Stock(underlier, "SMART", "USD")


def _ticker_spot(ticker) -> float:
    for attr in ("last", "close", "marketPrice"):
        value = getattr(ticker, attr, None)
        if callable(value):
            try:
                value = value()
            except Exception:
                continue
        if value is None:
            continue
        try:
            fval = float(value)
        except (TypeError, ValueError):
            continue
        if math.isfinite(fval) and fval > 0:
            return fval
    return float("nan")


def _ticker_iv(ticker) -> float:
    model = getattr(ticker, "modelGreeks", None)
    if model is not None:
        iv = getattr(model, "impliedVol", None)
        if iv is not None:
            try:
                return float(iv)
            except (TypeError, ValueError):
                pass
    iv = getattr(ticker, "impliedVolatility", None)
    try:
        return float(iv) if iv is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ticker_greek(ticker, name: str) -> float:
    model = getattr(ticker, "modelGreeks", None)
    if model is None:
        return float("nan")
    value = getattr(model, name, None)
    try:
        return float(value) if value is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")


def _ticker_oi(ticker, right: str) -> int:
    attr = "callOpenInterest" if right.upper() == "C" else "putOpenInterest"
    value = getattr(ticker, attr, None)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _ticker_volume(ticker) -> int:
    value = getattr(ticker, "volume", None)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _safe_float(value) -> float:
    try:
        fval = float(value) if value is not None else float("nan")
    except (TypeError, ValueError):
        return float("nan")
    return fval if math.isfinite(fval) else float("nan")


def _pick_option_params(params: list, exchange_hint: str | None):
    """Choose the OptionChain row matching the preferred exchange, or first available."""
    if not params:
        return None
    if exchange_hint:
        for row in params:
            if getattr(row, "exchange", None) == exchange_hint:
                return row
    for row in params:
        if getattr(row, "exchange", None) == "SMART":
            return row
    return params[0]


def _parse_expiry(raw: str) -> date | None:
    try:
        return datetime.strptime(raw, "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def fetch_chain_snapshot(
    underlier: str,
    *,
    expirations: list[date] | None = None,
) -> pd.DataFrame:
    """Fetch an options chain snapshot from IBKR for the given underlier.

    Returns a DataFrame with the canonical CHAIN_COLUMNS schema. Greeks and IV
    are populated from IBKR's model values; OI is per-contract.
    """
    setup_logging()
    settings = get_settings()
    ib_async_mod = _import_ib_async()

    ib = ib_async_mod.IB()
    try:
        try:
            ib.connect(
                settings.ibkr_host,
                settings.ibkr_port,
                clientId=settings.ibkr_client_id,
                readonly=True,
                timeout=10,
            )
        except Exception as exc:
            raise RuntimeError(
                f"IB Gateway/TWS not reachable at {settings.ibkr_host}:{settings.ibkr_port} "
                "-- is it running and logged in?"
            ) from exc

        ib.reqMarketDataType(settings.ibkr_market_data_type)

        # 1. Qualify underlier & get spot
        under = _build_underlier_contract(ib_async_mod, underlier)
        qualified = ib.qualifyContracts(under)
        if not qualified:
            logger.warning("{}: IBKR could not qualify underlier contract", underlier)
            return pd.DataFrame(columns=CHAIN_COLUMNS)
        under = qualified[0]

        under_tickers = ib.reqTickers(under)
        spot = _ticker_spot(under_tickers[0]) if under_tickers else float("nan")
        if not math.isfinite(spot) or spot <= 0:
            logger.warning("{}: IBKR returned no usable spot price", underlier)
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        # 2. Resolve available expirations + strikes
        sec_type = under.secType
        params = ib.reqSecDefOptParams(under.symbol, "", sec_type, under.conId)
        exchange_hint = UNDERLIER_EXCHANGE.get(underlier, (None, None))[1]
        chain = _pick_option_params(params, exchange_hint)
        if chain is None:
            logger.warning("{}: IBKR returned no option params", underlier)
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        available_exps = {
            parsed
            for raw in getattr(chain, "expirations", []) or []
            if (parsed := _parse_expiry(raw)) is not None
        }
        if expirations:
            target_exps = sorted(set(expirations) & available_exps)
        else:
            target_exps = sorted(available_exps)[:2]
        if not target_exps:
            logger.warning(
                "{}: IBKR has no requested expirations; requested={}, available_sample={}",
                underlier,
                [exp.isoformat() for exp in (expirations or [])],
                [exp.isoformat() for exp in sorted(available_exps)[:5]],
            )
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        lo = spot * (1 - _DEFAULT_STRIKE_BAND_PCT)
        hi = spot * (1 + _DEFAULT_STRIKE_BAND_PCT)
        strikes = sorted(
            float(k)
            for k in (getattr(chain, "strikes", []) or [])
            if lo <= float(k) <= hi
        )
        if not strikes:
            logger.warning("{}: no strikes within +/-{:.0%} of spot {:.2f}",
                           underlier, _DEFAULT_STRIKE_BAND_PCT, spot)
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        trading_class = getattr(chain, "tradingClass", "") or ""
        chain_exchange = getattr(chain, "exchange", "SMART") or "SMART"

        # 3. Build, qualify, and snapshot Option contracts
        contracts = []
        for exp in target_exps:
            exp_str = exp.strftime("%Y%m%d")
            for strike in strikes:
                for right in ("C", "P"):
                    opt = ib_async_mod.Option(
                        under.symbol,
                        exp_str,
                        strike,
                        right,
                        chain_exchange,
                        "100",
                        "USD",
                    )
                    if trading_class:
                        opt.tradingClass = trading_class
                    contracts.append(opt)

        qualified_opts = ib.qualifyContracts(*contracts) if contracts else []
        qualified_opts = [c for c in qualified_opts if getattr(c, "conId", 0)]
        if not qualified_opts:
            logger.warning("{}: IBKR qualified 0 option contracts", underlier)
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        snapshot_ts = datetime.now(tz=UTC)
        tickers = []
        for i in range(0, len(qualified_opts), _CHUNK_SIZE):
            batch = qualified_opts[i : i + _CHUNK_SIZE]
            tickers.extend(ib.reqTickers(*batch, regulatorySnapshot=False))

        records: list[dict] = []
        for t in tickers:
            contract = getattr(t, "contract", None)
            if contract is None:
                continue
            right = (getattr(contract, "right", "") or "").upper()
            expiry = _parse_expiry(getattr(contract, "lastTradeDateOrContractMonth", ""))
            if expiry is None or right not in ("C", "P"):
                continue
            records.append(
                {
                    "underlier": underlier,
                    "expiration": expiry,
                    "strike": float(getattr(contract, "strike", 0.0) or 0.0),
                    "option_type": "call" if right == "C" else "put",
                    "bid": _safe_float(getattr(t, "bid", None)),
                    "ask": _safe_float(getattr(t, "ask", None)),
                    "last": _safe_float(getattr(t, "last", None)),
                    "volume": _ticker_volume(t),
                    "open_interest": _ticker_oi(t, right),
                    "implied_volatility": _ticker_iv(t),
                    "delta": _ticker_greek(t, "delta"),
                    "gamma": _ticker_greek(t, "gamma"),
                    "theta": _ticker_greek(t, "theta"),
                    "vega": _ticker_greek(t, "vega"),
                    "spot": spot,
                    "snapshot_ts": snapshot_ts,
                }
            )

        if not records:
            logger.warning("{}: IBKR returned 0 option tickers", underlier)
            return pd.DataFrame(columns=CHAIN_COLUMNS)

        df = pd.DataFrame(records)
        df["volume"] = df["volume"].astype("int64")
        df["open_interest"] = df["open_interest"].astype("int64")
        df = df.sort_values(["expiration", "strike", "option_type"]).reset_index(drop=True)

        if df["implied_volatility"].isna().all():
            logger.warning(
                "{}: IBKR returned no IV/Greeks -- check OPRA subscription for the live account",
                underlier,
            )

        logger.info("{}: {} contracts fetched from IBKR", underlier, len(df))
        return df[CHAIN_COLUMNS]

    finally:
        try:
            if ib.isConnected():
                ib.disconnect()
        except Exception:
            pass


def fetch_previous_day_oi(underlier: str) -> pd.DataFrame:
    """Fetch chain snapshot for OI population (call after OCC settlement, ~08:00 ET)."""
    return fetch_chain_snapshot(underlier)
