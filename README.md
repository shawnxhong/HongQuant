# HongQuant

Personal mid-low-frequency quant system covering US equities/ETFs and crypto, with an options-structure signal layer feeding portfolio decisions.

See `plans/` for the phased build plan. Phase 0 scaffolding: package layout, DuckDB/Parquet data lake, adapters for Alpaca / yfinance / ccxt / SEC EDGAR / FRED, and Prefect flows for daily/hourly ingestion.

## Quick start

```bash
uv sync                          # install core deps
cp .env.example .env             # fill in keys you plan to use
docker compose up -d             # (optional) Postgres + Prefect server

# Run a flow locally
uv run python -m hongquant.flows.daily_equities --symbols SPY,QQQ,AAPL
```

Optional extras (install only what you need):

```bash
uv sync --extra research         # vectorbt, backtrader, alphalens, quantstats
uv sync --extra portfolio        # PyPortfolioOpt, Riskfolio-Lib
uv sync --extra options          # py_vollib
uv sync --extra llm              # LangChain, LanceDB
uv sync --extra ibkr             # ib_async
uv sync --extra dashboard        # Streamlit
```
