"""Polygon.io options chain snapshot adapter."""
from __future__ import annotations

import time
from datetime import UTC, date, datetime

import httpx
import pandas as pd
from tenacity import retry, stop_after_attempt, wait_exponential

from ...config import get_settings
from ...logging import logger, setup_logging

# Polygon uses "I:" prefix for cash-settled index options
UNDERLIER_MAP: dict[str, str] = {
    "SPX": "I:SPX",
    "NDX": "I:NDX",
    "VIX": "I:VIX",
}

_BASE = "https://api.polygon.io/v3/snapshot/options"

CHAIN_COLUMNS = [
    "underlier",
    "expiration",
    "strike",
    "option_type",
    "bid",
    "ask",
    "last",
    "volume",
    "open_interest",
    "implied_volatility",
    "delta",
    "gamma",
    "theta",
    "vega",
    "spot",
    "snapshot_ts",
]


def _parse_contract(raw: dict, underlier: str, snapshot_ts: datetime) -> dict | None:
    details = raw.get("details", {})
    greeks = raw.get("greeks", {})
    quote = raw.get("last_quote", {})
    day = raw.get("day", {})
    underlying = raw.get("underlying_asset", {})

    exp_str = details.get("expiration_date")
    strike = details.get("strike_price")
    opt_type = details.get("contract_type")
    if not exp_str or strike is None or not opt_type:
        return None

    return {
        "underlier": underlier,
        "expiration": date.fromisoformat(exp_str),
        "strike": float(strike),
        "option_type": str(opt_type).lower(),
        "bid": float(quote.get("bid") or 0),
        "ask": float(quote.get("ask") or 0),
        "last": float(day.get("close") or 0),
        "volume": int(day.get("volume") or 0),
        "open_interest": int(raw.get("open_interest") or 0),
        "implied_volatility": float(raw.get("implied_volatility") or 0) or float("nan"),
        "delta": float(greeks.get("delta") or 0) or float("nan"),
        "gamma": float(greeks.get("gamma") or 0) or float("nan"),
        "theta": float(greeks.get("theta") or 0) or float("nan"),
        "vega": float(greeks.get("vega") or 0) or float("nan"),
        "spot": float(underlying.get("price") or 0) or float("nan"),
        "snapshot_ts": snapshot_ts,
    }


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _get(client: httpx.Client, url: str, params: dict) -> dict:
    resp = client.get(url, params=params, timeout=30.0)
    resp.raise_for_status()
    return resp.json()


def fetch_chain_snapshot(
    underlier: str,
    *,
    expirations: list[date] | None = None,
    page_delay: float = 0.2,
) -> pd.DataFrame:
    """Fetch a full options chain snapshot from Polygon.io.

    Returns a DataFrame with one row per contract (CHAIN_COLUMNS).
    page_delay: seconds to sleep between paginated requests (respect rate limits).
    """
    setup_logging()
    settings = get_settings()
    if not settings.polygon_api_key:
        raise RuntimeError("POLYGON_API_KEY not set in environment")

    polygon_ticker = UNDERLIER_MAP.get(underlier, underlier)
    snapshot_ts = datetime.now(tz=UTC)

    records: list[dict] = []
    url = f"{_BASE}/{polygon_ticker}"
    params: dict = {"limit": 250, "apiKey": settings.polygon_api_key}

    if expirations and len(expirations) == 1:
        params["expiration_date"] = expirations[0].isoformat()

    with httpx.Client() as client:
        while url:
            data = _get(client, url, params)
            for raw in data.get("results", []):
                record = _parse_contract(raw, underlier, snapshot_ts)
                if record is not None:
                    records.append(record)

            next_url = data.get("next_url")
            if next_url:
                url = next_url
                params = {"apiKey": settings.polygon_api_key}
                if page_delay > 0:
                    time.sleep(page_delay)
            else:
                url = ""

    if not records:
        logger.warning("{}: Polygon returned 0 contracts", underlier)
        return pd.DataFrame(columns=CHAIN_COLUMNS)

    df = pd.DataFrame(records)

    # Client-side expiration filter when multiple expirations requested
    if expirations and len(expirations) > 1:
        exp_set = set(expirations)
        df = df[df["expiration"].isin(exp_set)]

    logger.info("{}: {} contracts fetched from Polygon", underlier, len(df))
    return df[CHAIN_COLUMNS].reset_index(drop=True)


def fetch_previous_day_oi(underlier: str) -> pd.DataFrame:
    """Fetch chain snapshot for OI population (best called at 08:00 ET after OCC settlement)."""
    return fetch_chain_snapshot(underlier)
