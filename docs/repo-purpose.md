# HongQuant Repo Purpose

## What This Repository Is For

HongQuant is a personal quant research and signal-generation codebase for a single operator.
It is being built to support a mid/low-frequency investment workflow across:

- US equities and ETFs
- Crypto spot markets
- Macro data and SEC filings as supporting research inputs

The repo is not intended to be a generic quant platform, a broker-integrated execution system, or a product for external users.
Its purpose is to give one investor a maintainable local codebase that can:

1. Ingest and normalize market and research data from reusable open-source adapters.
2. Store that data in a lightweight local lakehouse layout.
3. Run scheduled pipelines that refresh data and prepare downstream research inputs.
4. Evolve into a decision-support system that produces signals, portfolio suggestions, and reports.


## Why It Exists

The development conversation makes the intent explicit:

- this is a personal system, so infrastructure should stay lightweight and easy to maintain
- existing open-source tools should be reused wherever possible
- the first milestone is not full automated trading, but a solid research and data foundation
- execution is expected to be semi-automatic at first: the system produces signals and recommendations, and the user decides how to act on them

That leads to a practical architecture:

- Parquet + DuckDB instead of heavy data infrastructure
- Prefect for simple scheduled workflows
- provider adapters instead of building proprietary data plumbing
- clear package boundaries for future strategy, portfolio, LLM, and reporting layers


## Current Scope in This Repo

Today, the implemented code is mostly Phase 0 infrastructure.
The repository already provides:

- canonical OHLCV normalization and validation
- a Parquet data lake partitioned by market, asset type, interval, and year
- DuckDB-backed querying over that lake
- environment-based configuration
- a curated research universe in `configs/universe.yaml`
- data adapters for Alpaca, yfinance, ccxt, FRED, and SEC EDGAR
- Prefect flows for daily US equities/ETF ingestion and hourly crypto ingestion
- Telegram notification plumbing
- tests for schema, storage idempotency, and universe loading

In other words, the repo currently functions as a data and orchestration foundation for later quantitative research.


## Intended End State

Based on the code layout and the dev conversation, the repo is meant to grow into a four-layer personal quant stack:

- Data layer: ingest price, macro, and filing data into a normalized local store
- Research and signal layer: implement factor logic, momentum/CTA ideas, and later options-structure signals
- Decision layer: combine signals into target weights using portfolio and risk rules
- Delivery layer: generate reports, alerts, and position guidance for manual or semi-manual execution

There is also an explicit plan to add an LLM-assisted research pipeline for earnings filings and valuation support.
That LLM layer is intended to complement, not replace, the quantitative signal stack.


## What This Repo Is Not

This repository is currently not:

- a production OMS/EMS
- a low-latency or high-frequency trading system
- a broker-agnostic live execution engine
- a public framework intended for broad third-party customization
- a complete backtesting or portfolio platform yet

Several packages already exist for those future concerns, but most are scaffolding placeholders at this stage.


## Practical Summary

The purpose of HongQuant is to become a personal, modular, open-source-heavy quant operating system for mid/low-frequency investing.

Right now, its real job is narrower and more concrete:

- centralize data ingestion
- enforce a consistent storage schema
- make scheduled data refresh reliable
- create a clean foundation for future strategy, portfolio, LLM, and reporting work

If someone opens this repo today, they should understand it as an early-stage personal quant infrastructure project with a working data layer and a clearly defined path toward signal generation and portfolio decision support.
