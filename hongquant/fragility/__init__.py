"""Trend flash-crash radar.

Daily conditional-fragility scoring over a themed watchlist (gold, hot stocks,
ETFs). A flash crash needs three things co-occurring — Extension (A),
Crowding & Leverage (B), and Fragility / dealer reflexivity (C) — gated by a
market-level systemic factor. The output is a continuous 0-100 knob that drives
position-sizing / hedging, never entry/exit timing.

See ``src/趋势闪崩预警系统_设计方案.md`` for the design rationale.
"""
