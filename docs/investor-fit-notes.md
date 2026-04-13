# Investor Fit Notes

Date: 2026-04-13

## Context

These notes are for the current owner/operator of HongQuant:

- personal fund size around `$600,000`
- about `9` years of BTC trading experience
- about `1` year of US stock experience
- not strongly profitable yet
- but capital preservation has been solid, with no total drawdown worse than about `10%`


## High-Level Assessment

HongQuant can be genuinely useful if it becomes a system for:

- measuring real edge
- improving position sizing
- reducing low-quality trades
- enforcing discipline
- helping the operator stay inside a narrow circle of competence

HongQuant will not create alpha by itself.
Its value is in improving decision quality, risk allocation, and consistency.


## What Matters Most For This Investor

The strongest signal is not raw profitability yet, but survival and drawdown control.
That suggests the operator likely has some risk discipline already.

The probable bottlenecks are:

- unclear or unmeasured edge
- insufficient selectivity
- insufficient concentration when odds are unusually favorable
- too much time spent on research infrastructure that does not improve actual decisions


## What HongQuant Should Do

For this investor profile, the system should primarily:

1. identify which setups, markets, and holding periods actually make money
2. separate real signal from noise
3. improve bet sizing and portfolio concentration
4. reduce avoidable mistakes
5. support patient decision-making rather than increase activity


## What To Build First

Highest expected ROI:

- trade journal and performance attribution
- benchmark comparison versus BTC buy-and-hold, SPY, and cash
- position sizing and drawdown rules
- regime filters
- watchlist workflow and execution checklist
- earnings / filing summarization only for a very small number of US names actually followed


## What To Delay Or Cut

Lower expected ROI at the current stage:

- broad multi-market expansion before a proven edge exists
- complex portfolio optimization too early
- generic LLM trade recommendations
- wide stock coverage without real follow depth
- options-structure analytics before core spot/equity process is proven
- research features that increase activity without improving selectivity


## Working Principle

HongQuant should be treated as a decision-quality system, not a signal factory.

The right outcome is not:

- more trades
- more indicators
- more models
- more dashboards

The right outcome is:

- fewer but better decisions
- clearer sizing
- stronger review of mistakes
- stronger concentration when conviction is justified


## Practical Build Order

Recommended order for this repo:

1. performance measurement and attribution
2. decision checklist and journaling workflow
3. simple regime and sizing rules
4. one narrow strategy loop with real historical validation
5. small-scale filing / earnings research support

Only after those work in practice should the repo expand into:

- broader portfolio construction
- options overlays
- richer LLM agents
- additional markets


## Concrete Recommendation For The Current Operator

If prioritization must be strict, build in this order:

1. a real decision ledger
2. performance attribution by market, setup, holding period, and regime
3. benchmark comparison versus BTC buy-and-hold, SPY, and cash
4. simple sizing and drawdown rules
5. one narrow strategy loop in a single domain
6. a small LLM research assistant only for a short watchlist

The narrow strategy loop should be only one of:

- BTC swing / regime trading
- US ETF / megacap medium-term trading

Do not try to industrialize both at once until one loop is demonstrably useful.


## Concrete Recommendation On What To Cut Or Delay

Until a repeatable edge is measured, delay or cut:

- A-share expansion
- broad multi-market coverage
- options-structure analytics
- generic LLM trade recommendations
- sophisticated portfolio optimization
- rich dashboards
- TradingView webhook integration
- any feature whose main effect is increasing trade frequency


## Short Rule

Build in this sequence:

- measurement
- sizing
- one narrow edge loop

Cut almost everything else until those three are working in practice.


## Summary

For this investor, HongQuant is worth building only if it helps answer:

- what is my real edge?
- when should I do nothing?
- when should I size up?
- which mistakes repeat?

If the system cannot answer those questions, it is probably becoming too complicated.
