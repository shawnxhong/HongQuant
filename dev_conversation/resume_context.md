# Resume Context

Use this file when resuming the project from another machine or another CLI.

## Minimal Load Set

Read only these two files first:

- `dev_conversation/2026-04-13-152913-local-command-caveatcaveat-the-messages-below.txt`
- `docs/repo-purpose.md`

That gives enough context for most follow-up work without loading the old full transcript.

## One-Paragraph Handoff

HongQuant is a personal mid/low-frequency quant system for US equities/ETFs and crypto, with future A-share support. The design direction is lightweight and open-source-heavy: Parquet + DuckDB for the data layer, Prefect for orchestration, provider adapters for ingestion, and later layers for signals, portfolio decisions, LLM-assisted filings/valuation, and reporting. The repo currently has Phase 0 infrastructure implemented and tested: canonical OHLCV schema, Parquet/DuckDB storage, Alpaca/yfinance/ccxt/EDGAR/FRED adapters, daily/hourly Prefect ingestion flows, universe config, notifications, and tests. TradingView is intended only for charting/prototyping/alerts, not as the main data source or backtest engine.

## Suggested Resume Prompt

```text
Read `dev_conversation/2026-04-13-152913-local-command-caveatcaveat-the-messages-below.txt` and `docs/repo-purpose.md`. Treat them as the compact handoff for this repo. Then continue work on HongQuant from the current Phase 0 state without re-deriving the project purpose.
```
