from __future__ import annotations

import sys
import types
from datetime import date
from typing import ClassVar

import pytest

from hongquant.options.adapters.polygon_options import CHAIN_COLUMNS


class _ModelGreeks:
    def __init__(self, delta=0.5, gamma=0.01, theta=-0.02, vega=0.15, impliedVol=0.25):
        self.delta = delta
        self.gamma = gamma
        self.theta = theta
        self.vega = vega
        self.impliedVol = impliedVol


class _Contract:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
        if not getattr(self, "conId", None):
            self.conId = 1


def _make_stock(symbol, exchange="SMART", currency="USD"):
    return _Contract(symbol=symbol, exchange=exchange, currency=currency, secType="STK", conId=1000)


def _make_index(symbol, exchange="CBOE", currency="USD"):
    return _Contract(symbol=symbol, exchange=exchange, currency=currency, secType="IND", conId=2000)


def _make_option(symbol, expiry, strike, right, exchange, multiplier, currency):
    return _Contract(
        symbol=symbol,
        lastTradeDateOrContractMonth=expiry,
        strike=float(strike),
        right=right,
        exchange=exchange,
        multiplier=multiplier,
        currency=currency,
        secType="OPT",
        conId=hash((symbol, expiry, strike, right)) & 0xFFFFFF,
    )


class _Ticker:
    def __init__(self, contract, **kwargs):
        self.contract = contract
        self.bid = kwargs.get("bid", 1.0)
        self.ask = kwargs.get("ask", 1.2)
        self.last = kwargs.get("last", 1.1)
        self.volume = kwargs.get("volume", 50)
        self.callOpenInterest = kwargs.get("callOpenInterest", 500)
        self.putOpenInterest = kwargs.get("putOpenInterest", 400)
        self.modelGreeks = kwargs.get("modelGreeks", _ModelGreeks())


class _OptionChain:
    def __init__(self, exchange, trading_class, expirations, strikes):
        self.exchange = exchange
        self.tradingClass = trading_class
        self.expirations = list(expirations)
        self.strikes = list(strikes)


class _FakeIB:
    """Configurable mock IB; tests tweak class attributes before constructing."""

    spot = 500.0
    option_params: ClassVar[list] = []
    underlier_qualifies = True

    def __init__(self):
        self._connected = False

    def connect(self, host, port, clientId=1, readonly=False, timeout=10):
        self._connected = True

    def disconnect(self):
        self._connected = False

    def isConnected(self):
        return self._connected

    def reqMarketDataType(self, t):
        return None

    def qualifyContracts(self, *contracts):
        if not self.underlier_qualifies and len(contracts) == 1 and contracts[0].secType in {"STK", "IND"}:
            return []
        return list(contracts)

    def reqTickers(self, *contracts, regulatorySnapshot=False):
        out = []
        for c in contracts:
            if c.secType in {"STK", "IND"}:
                out.append(_Ticker(c, last=self.spot, bid=self.spot - 0.1, ask=self.spot + 0.1))
            else:
                out.append(_Ticker(c))
        return out

    def reqSecDefOptParams(self, symbol, exchange, secType, conId):
        return list(self.option_params)


def _install_fake_ib(monkeypatch, *, spot=500.0, option_params=None, qualifies=True):
    fake_mod = types.ModuleType("ib_async")
    fake_mod.IB = _FakeIB
    fake_mod.Stock = _make_stock
    fake_mod.Index = _make_index
    fake_mod.Option = _make_option

    _FakeIB.spot = spot
    _FakeIB.option_params = option_params or []
    _FakeIB.underlier_qualifies = qualifies

    monkeypatch.setitem(sys.modules, "ib_async", fake_mod)
    return fake_mod


def test_ibkr_adapter_normalizes_chain(monkeypatch):
    chain = _OptionChain(
        exchange="SMART",
        trading_class="SPY",
        expirations=["20260515", "20260522"],
        strikes=[490.0, 495.0, 500.0, 505.0, 510.0],
    )
    _install_fake_ib(monkeypatch, spot=500.0, option_params=[chain])

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    df = fetch_chain_snapshot("SPY")

    assert list(df.columns) == CHAIN_COLUMNS
    # 2 expirations x 5 strikes x 2 rights = 20 rows
    assert len(df) == 20
    assert set(df["option_type"]) == {"call", "put"}
    assert set(df["underlier"]) == {"SPY"}
    assert df["spot"].iloc[0] == 500.0
    assert df["implied_volatility"].between(0.0, 1.0).all()
    assert df["delta"].notna().all()
    assert df["open_interest"].sum() > 0


def test_ibkr_adapter_empty_when_no_option_params(monkeypatch):
    _install_fake_ib(monkeypatch, spot=500.0, option_params=[])

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    df = fetch_chain_snapshot("SPY")

    assert df.empty
    assert list(df.columns) == CHAIN_COLUMNS


def test_ibkr_adapter_filters_to_requested_expirations(monkeypatch):
    chain = _OptionChain(
        exchange="SMART",
        trading_class="SPY",
        expirations=["20260515", "20260522"],
        strikes=[495.0, 500.0, 505.0],
    )
    _install_fake_ib(monkeypatch, spot=500.0, option_params=[chain])

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    df = fetch_chain_snapshot("SPY", expirations=[date(2026, 5, 15)])

    assert not df.empty
    assert set(df["expiration"]) == {date(2026, 5, 15)}
    # 1 expiration x 3 strikes x 2 rights = 6 rows
    assert len(df) == 6


def test_ibkr_adapter_index_underlier_uses_index_contract(monkeypatch):
    chain = _OptionChain(
        exchange="CBOE",
        trading_class="SPX",
        expirations=["20260515"],
        strikes=[4900.0, 5000.0, 5100.0],
    )
    _install_fake_ib(monkeypatch, spot=5000.0, option_params=[chain])

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    df = fetch_chain_snapshot("SPX", expirations=[date(2026, 5, 15)])

    assert not df.empty
    assert set(df["underlier"]) == {"SPX"}
    assert df["spot"].iloc[0] == 5000.0


def test_ibkr_adapter_raises_when_module_missing(monkeypatch):
    monkeypatch.setitem(sys.modules, "ib_async", None)

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    with pytest.raises(RuntimeError, match="ib_async is not installed"):
        fetch_chain_snapshot("SPY")


def test_ibkr_adapter_returns_empty_when_underlier_not_qualified(monkeypatch):
    chain = _OptionChain(
        exchange="SMART", trading_class="SPY", expirations=["20260515"], strikes=[500.0]
    )
    _install_fake_ib(monkeypatch, spot=500.0, option_params=[chain], qualifies=False)

    from hongquant.options.adapters.ibkr_options import fetch_chain_snapshot

    df = fetch_chain_snapshot("UNKNOWN")
    assert df.empty
    assert list(df.columns) == CHAIN_COLUMNS
