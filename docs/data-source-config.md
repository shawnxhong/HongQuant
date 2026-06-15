# HongQuant Data Source and API Key Configuration

This file is the operational checklist for `.env` and the weekly self-check.
The self-check command is:

```bash
uv run python -m hongquant.diagnostics.weekly_self_check
uv run python -m hongquant.diagnostics.weekly_self_check --json --no-notify
```

By default it sends one Telegram message and one email summary. Use `--no-notify` for local dry runs.

## Required for Core Scheduled Checks

| Area | Env vars | Used by | Notes |
| --- | --- | --- | --- |
| FRED macro | `FRED_API_KEY` | LRM, fragility systemic gate, macro context | Free key. Required for liquidity and systemic-risk data. |
| Yahoo Finance | none | equity pulse, fragility prices, yfinance options fallback | Free public source; no key. |
| DefiLlama | none | LRM stablecoin risk appetite | Free public source; no key. |
| CFTC COT | none | fragility gold/silver crowding | Free public source through `cot_reports`. |
| SEC EDGAR | `EDGAR_USER_AGENT` | filings/facts research adapters | Must include contact info for fair access. |
| Options provider | `OPTIONS_DATA_PROVIDER` plus provider-specific config | OpEx risk, fragility option-chain inputs | `yfinance` needs no key; `polygon` needs `POLYGON_API_KEY`; `ibkr` needs Gateway/TWS. |
| Anthropic | `ANTHROPIC_API_KEY`, optional `ANTHROPIC_SELF_CHECK_MODEL` | current in-repo LLM client and self-check | Current production LLM code is Anthropic-only. |
| DeepSeek | `DEEPSEEK_API_KEY`, optional `DEEPSEEK_MODEL` | weekly self-check and external Hermes/agent workflow | Direct self-check uses DeepSeek's OpenAI-compatible chat endpoint. |
| Telegram | `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | alerts and self-check summary | Self-check sends a real test summary unless `--no-notify` is used. |
| Email | `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM`, `SMTP_TO` | OpEx/LRM reports and self-check summary | Gmail app-password works. |

## Conditional or Optional Sources

| Source | Env/config | When it becomes required | Notes |
| --- | --- | --- | --- |
| Alpaca | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER` | If `daily_equities --source alpaca` is your scheduled source | Otherwise yfinance can backfill OHLCV. |
| Polygon options | `POLYGON_API_KEY`, `OPTIONS_DATA_PROVIDER=polygon` | If selected as the options provider | Needed for paid/live option snapshots. |
| IBKR options | `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_MARKET_DATA_TYPE`, `OPTIONS_DATA_PROVIDER=ibkr` | If selected as the options provider | Requires TWS or IB Gateway running and market-data subscriptions. |
| CCXT public crypto | optional exchange keys | Public OHLCV works without keys for many exchanges | Weekly self-check probes Binance public BTC/USDT as optional by default. |
| OpenAI | `OPENAI_API_KEY` | Not required today | Config field exists, but no core flow uses it yet. |
| FMP/Finnhub/Tiingo | `FMP_API_KEY`, `FINNHUB_API_KEY`, `TIINGO_API_KEY` | Not required today | Config fields exist for future data adapters. |

## Weekly Self-Check Behavior

- Required failures make the command exit with code `1`.
- Optional sources are `SKIP` when unconfigured and `WARN` when configured but failing.
- `--strict-optional` turns optional checks into required checks for full production audits.
- Secrets are never printed; only missing env var names are shown.
- Default latency thresholds are conservative: source checks 30s, LLM checks 45s, total run 300s.
