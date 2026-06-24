# HongQuant Data Source and API Key Configuration

This file is the operational checklist for `.env` and the weekly self-check.
The self-check command is:

```bash
uv run python -m hongquant.diagnostics.weekly_self_check
uv run python -m hongquant.diagnostics.weekly_self_check --json
```

It prints the summary to stdout. Delivery to Telegram/WeChat/Email is handled by the Hermes agent, which runs the check on schedule and routes its output — HongQuant itself holds no messaging credentials.

## Current Status — action items (self-check 2026-06-16, `--strict-optional`)

Everything the **default configuration** needs is working. The only *required* failure is Anthropic (a billing issue, not a config one). The remaining failures are optional capabilities you only need if you enable those paths.

| Source | Status | What to do |
| --- | --- | --- |
| FRED, Yahoo (OHLCV + options), DefiLlama, CFTC COT, SEC EDGAR, DeepSeek, Alpaca | ✅ PASS | Nothing — configured and reachable. |
| **Anthropic** | ❌ FAIL — `400 credit balance too low` | Key is valid; the **account has no credits**. Add credits at <https://console.anthropic.com> → *Plans & Billing*. Until then the Anthropic-only LLM layers (fragility red-team narrative, LRM advisory synthesis) stay dark — both are designed to degrade gracefully, so the mechanical scores/reports still run. |
| **Polygon options** | ❌ FAIL — `403 NOT_AUTHORIZED` | Key is valid but your **Polygon plan is not entitled to options snapshots** (`/v3/snapshot/options`). Either upgrade to a Polygon plan that includes Options, or leave `OPTIONS_DATA_PROVIDER=yfinance` (the working default). Only needed if you switch the provider to `polygon`. |
| **Crypto exchanges (CCXT)** | ⏭️ not configured | Crypto isn't wired into any scheduled flow, so this is expected. The self-check's default Binance probe timed out at run time, but that's not a key or account issue — you plan to use **OKX** instead. Apply for an OKX key (see *Affordable add-on data sources* below) and run `hourly_crypto --exchange okx` when you want crypto ingest. |
| **IBKR options** | ❌ FAIL — `ib_async is not installed` | Optional. Only if you set `OPTIONS_DATA_PROVIDER=ibkr`: run `uv sync --extra ibkr`, then start TWS / IB Gateway with the API enabled and matching `IBKR_HOST`/`IBKR_PORT`. |

Note: `OPENAI_API_KEY` is set but unused by any core flow today; no action needed.

Re-run `uv run python -m hongquant.diagnostics.weekly_self_check --json` after each fix to confirm the status flips to PASS.

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

Alerts and reports are emitted to stdout; the Hermes agent owns delivery to Telegram, WeChat, and Email, so no messaging credentials live in this repo's `.env`.

## Conditional or Optional Sources

| Source | Env/config | When it becomes required | Notes |
| --- | --- | --- | --- |
| Alpaca | `ALPACA_API_KEY`, `ALPACA_API_SECRET`, `ALPACA_PAPER` | If `daily_equities --source alpaca` is your scheduled source | Otherwise yfinance can backfill OHLCV. |
| Polygon options | `POLYGON_API_KEY`, `OPTIONS_DATA_PROVIDER=polygon` | If selected as the options provider | Needed for paid/live option snapshots. |
| IBKR options | `IBKR_HOST`, `IBKR_PORT`, `IBKR_CLIENT_ID`, `IBKR_MARKET_DATA_TYPE`, `OPTIONS_DATA_PROVIDER=ibkr` | If selected as the options provider | Requires TWS or IB Gateway running and market-data subscriptions. |
| CCXT crypto | exchange keys optional | If you schedule `hourly_crypto` | Public OHLCV needs no key. Pick the venue with `--exchange` (default `binance`). **OKX** needs key + secret + passphrase. Self-check probes Binance public BTC/USDT. |
| OpenAI | `OPENAI_API_KEY` | Not required today | Config field exists, but no core flow uses it yet. |
| Affordable equities/macro | `FMP_API_KEY`, `FINNHUB_API_KEY`, `TIINGO_API_KEY`, `ALPHAVANTAGE_API_KEY`, `TWELVEDATA_API_KEY` | Not required today | Free-tier fallbacks for OHLCV, fundamentals, and earnings/economic calendars. Key slots ready; adapters are future work. See *Affordable add-on data sources* below. |

## Affordable add-on data sources (how to apply)

These fill the gaps the free defaults leave: yfinance rate-limits intermittently, and
there is no dedicated earnings/economic-calendar feed yet. Each has a usable free tier.
The key slots already exist in `.env.example` and `config.py`. **Adapter status:** OKX
works today through the existing `ccxt` adapter; the equities/fundamentals providers
below are key slots whose adapters are future work — applying now just makes the key
available when the adapter lands. To use any of them, paste the key into `.env`.

### OKX — crypto OHLCV (ccxt)
- **Gives:** spot/perp OHLCV for the `hourly_crypto` flow, as an alternative venue to Binance.
- **Free:** public market data needs no key; keys only raise rate limits / unlock private endpoints.
- **Apply:** <https://www.okx.com> → Account → API → *Create API key (V5)*. You get **three** values — API key, secret key, and a passphrase you choose. Put them in `OKX_API_KEY`, `OKX_API_SECRET`, `OKX_API_PASSPHRASE`.
- **Use:** `uv run python -m hongquant.flows.hourly_crypto --exchange okx --symbols BTC/USDT,ETH/USDT`.

### Alpha Vantage — equities / FX / economic indicators
- **Gives:** a free fallback for daily OHLCV when yfinance rate-limits, plus FX and economic-indicator series that complement the FRED-driven macro/LRM context.
- **Free:** 25 requests/day, 5/min. Instant key, no credit card.
- **Apply:** <https://www.alphavantage.co/support/#api-key> → enter an email → copy the key into `ALPHAVANTAGE_API_KEY`.

### Twelve Data — equities / FX / crypto + technical indicators
- **Gives:** another OHLCV fallback with built-in technical indicators and a much larger free quota than Alpha Vantage.
- **Free:** 800 requests/day, 8/min.
- **Apply:** <https://twelvedata.com/pricing> → *Basic (Free)* → sign up → API key into `TWELVEDATA_API_KEY`.

### Financial Modeling Prep (FMP) — earnings & economic calendars, fundamentals
- **Gives:** earnings calendar and economic calendar (directly feeds the OpEx agent's event calendar and fragility event windows) plus company fundamentals.
- **Free:** ~250 requests/day.
- **Apply:** <https://site.financialmodelingprep.com/developer/docs> → register → key into `FMP_API_KEY`.

### Finnhub — earnings / IPO calendar, news
- **Gives:** earnings and IPO calendars and market news/sentiment.
- **Free:** 60 requests/min.
- **Apply:** <https://finnhub.io> → sign up → key into `FINNHUB_API_KEY`.

### Tiingo — EOD prices, news, crypto (you already have a key)
- **Gives:** clean end-of-day equity prices, a news feed, and crypto.
- **Free:** limited symbols/hour, generous for daily EOD.
- **Apply:** <https://www.tiingo.com> → API → token into `TIINGO_API_KEY`.

### CoinGecko — keyless crypto market data (optional)
- **Gives:** broad crypto prices and market caps over plain HTTP (no exchange API), handy if exchange endpoints are unreachable. Complements DefiLlama on the liquidity side.
- **Free:** light use needs no key; a free *Demo* key raises limits. No config slot yet — listed for awareness.
- **Apply (optional):** <https://www.coingecko.com/en/api> → *Demo* plan.

## Weekly Self-Check Behavior

- Required failures make the command exit with code `1`.
- Optional sources are `SKIP` when unconfigured and `WARN` when configured but failing.
- `--strict-optional` turns optional checks into required checks for full production audits.
- Secrets are never printed; only missing env var names are shown.
- Default latency thresholds are conservative: source checks 30s, LLM checks 45s, total run 300s.
