from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from hongquant.flows import equity_pulse as flow_mod


def _synthetic_ohlcv(symbols_to_shapes: dict[str, np.ndarray]) -> pd.DataFrame:
    """Build a long-form OHLCV frame from {symbol -> close-price array}."""
    rows = []
    for symbol, closes in symbols_to_shapes.items():
        ts = pd.date_range("2025-05-15", periods=len(closes), freq="B", tz="UTC")
        for t, c in zip(ts, closes, strict=True):
            rows.append(
                {
                    "symbol": symbol,
                    "ts": t,
                    "open": c,
                    "high": c,
                    "low": c,
                    "close": float(c),
                    "volume": 1000.0,
                    "market": "us",
                    "asset_type": "equity",
                    "interval": "1d",
                    "source": "test",
                }
            )
    return pd.DataFrame(rows)


def _shape_breakout(n: int = 260) -> np.ndarray:
    # Smooth uptrend; latest close == 260-bar max
    return np.linspace(100.0, 200.0, n)


def _shape_drawdown(n: int = 260) -> np.ndarray:
    # Climbs to ~150 around bar 130, then drops to ~110 -> ~25% drawdown
    peak = np.linspace(100.0, 150.0, n // 2)
    drop = np.linspace(150.0, 110.0, n - n // 2)
    return np.concatenate([peak, drop])


def _shape_flat(n: int = 260, level: float = 100.0) -> np.ndarray:
    return np.full(n, level)


def _shape_mild_up(n: int = 260) -> np.ndarray:
    return np.linspace(95.0, 102.0, n)


def test_compute_snapshot_columns_and_breakout_detection(monkeypatch):
    history = _synthetic_ohlcv(
        {
            "BREAK": _shape_breakout(),
            "DD": _shape_drawdown(),
            "FLAT": _shape_flat(),
            "MILD": _shape_mild_up(),
        }
    )
    snapshot = flow_mod.compute_snapshot.fn(history)

    expected_cols = {
        "symbol", "close",
        "ret_1d", "ret_5d", "ret_20d", "ret_60d",
        "dist_50dma", "dist_200dma", "dist_52w_high", "drawdown_6m", "rsi_14",
    }
    assert expected_cols.issubset(snapshot.columns)
    assert set(snapshot["symbol"]) == {"BREAK", "DD", "FLAT", "MILD"}

    # Breakout symbol sits at its 52w high
    break_row = snapshot.set_index("symbol").loc["BREAK"]
    assert break_row["dist_52w_high"] == 0.0

    # Drawdown symbol is materially below trailing peak
    dd_row = snapshot.set_index("symbol").loc["DD"]
    assert dd_row["drawdown_6m"] < -0.10


def test_render_pulse_includes_breakout_and_drawdown_sections():
    history = _synthetic_ohlcv(
        {
            "BREAK": _shape_breakout(),
            "DD": _shape_drawdown(),
            "FLAT": _shape_flat(),
            "MILD": _shape_mild_up(),
        }
    )
    snapshot = flow_mod.compute_snapshot.fn(history)
    text = flow_mod.render_pulse.fn(snapshot, today=date(2026, 5, 12))

    assert "Equity Pulse" in text
    assert "Scanned 4" in text
    assert "Near 52w high" in text
    assert "BREAK" in text
    assert "Drawdown alerts" in text
    assert "DD" in text


def test_render_pulse_drops_empty_sections():
    # All four symbols are calm: no breakouts, no drawdowns
    history = _synthetic_ohlcv(
        {
            "A": _shape_flat(level=100.0),
            "B": _shape_flat(level=110.0),
            "C": _shape_flat(level=120.0),
            "D": _shape_flat(level=130.0),
        }
    )
    snapshot = flow_mod.compute_snapshot.fn(history)
    text = flow_mod.render_pulse.fn(snapshot, today=date(2026, 5, 12))

    # Flat series with no losses & no gains -> RSI undefined, returns 0% etc.
    # The breakout/drawdown thresholds should not trigger sections.
    assert "Drawdown alerts" not in text
    # Note: each flat symbol IS technically at its own 52w high (constant series),
    # so "Near 52w high" CAN appear. We don't assert on that.


def test_render_pulse_handles_empty_snapshot():
    text = flow_mod.render_pulse.fn(pd.DataFrame(), today=date(2026, 5, 12))
    assert "No data" in text


def test_load_history_empty_symbols_returns_empty():
    out = flow_mod.load_history.fn([])
    assert out.empty


def test_load_history_calls_query_ohlcv_with_market_us(monkeypatch):
    captured: dict = {}

    def fake_query(symbols, *, interval, market, start, **kwargs):
        captured["symbols"] = list(symbols)
        captured["interval"] = interval
        captured["market"] = market
        captured["start"] = start
        return _synthetic_ohlcv({"BREAK": _shape_breakout()})

    monkeypatch.setattr(flow_mod.store, "query_ohlcv", fake_query)

    df = flow_mod.load_history.fn(["BREAK"])

    assert captured["symbols"] == ["BREAK"]
    assert captured["interval"] == "1d"
    assert captured["market"] == "us"
    assert not df.empty


def test_load_history_returns_empty_when_query_raises(monkeypatch):
    """Cold-start case: parquet lake is empty, DuckDB raises IOException."""

    def fake_query(symbols, **kwargs):
        raise OSError(
            'IO Error: No files found that match the pattern "data/parquet/ohlcv/**/*.parquet"'
        )

    monkeypatch.setattr(flow_mod.store, "query_ohlcv", fake_query)

    df = flow_mod.load_history.fn(["SPY", "QQQ"])
    assert df.empty


def test_deliver_dry_run_does_not_notify(monkeypatch):
    calls = {"notify": 0}
    monkeypatch.setattr(flow_mod, "notify", lambda _t: calls.__setitem__("notify", calls["notify"] + 1))

    flow_mod.deliver.fn("hello", channels=["telegram"], dry_run=True)
    assert calls["notify"] == 0

    flow_mod.deliver.fn("hello", channels=["telegram"], dry_run=False)
    assert calls["notify"] == 1
