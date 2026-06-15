"""Liquidity Regime Monitor (LRM) — monthly regime conditioner.

Reads four layers of liquidity data (price of money, plumbing, private
risk-taking, global) plus central-bank text and outputs the current quadrant
(Q1-Q4), an active-sleeve water level, leverage rules, and daily interrupt
alerts. It answers "how big should risk be right now?" — it never emits
buy/sell signals (spec §0 non-goals are hard constraints).

Third system in the suite, sibling to ``hongquant.options`` and
``hongquant.fragility``. Its state-card JSON (``liquidity.statecard``) is the
contract the fragility system reads for its quadrant multiplier.
"""
