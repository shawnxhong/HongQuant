# Resume Context

Use this file when resuming the project from another machine or another Claude session.

## Minimal Load Set

Read only these files first:

- `docs/repo-purpose.md`
- `src/option_watch/plan.md`
- `src/option_watch/README.md`

That gives enough context for most follow-up work.

## One-Paragraph Handoff

HongQuant is a personal mid/low-frequency quant system for US equities/ETFs and crypto. Phase 0 infrastructure is done: canonical OHLCV schema, Parquet/DuckDB storage, Alpaca/yfinance/ccxt/EDGAR/FRED adapters, daily/hourly Prefect ingestion flows, universe config, Telegram notifications, and tests. **Phase 1 (first feature work) just shipped: the OpEx Momentum Risk Agent** (`hongquant/options/`). It scans SPY/QQQ/SMH/SOXX options for OpEx pressure every Wednesday before US close, computes a 0-100 Momentum Crash Risk Score, and sends a rich email + Telegram pulse. The agent is fully implemented and tested (52/52 tests pass, ruff clean); it needs live credentials wired and Prefect schedules registered before it runs in production.

---

## OpEx Risk Agent -- Current Status (as of 2026-05-10)

### What is built and tested

All logic lives in `hongquant/options/`. File map:

```
hongquant/
  options/
    __init__.py
    types.py               <- Event, SnapshotBundle, RiskScore dataclasses
    expiries.py            <- front_friday, monthly_opex, triple_witching helpers
    events.py              <- FOMC / CPI / NFP / earnings EventCalendar
    metrics.py             <- atm_iv, iv_term_structure, OI, gamma, max_pain, etc.
    momentum.py            <- QQQ/SPY & SMH/QQQ relative strength, breadth
    store.py               <- options snapshot Parquet store (DuckDB queries)
    risk_score.py          <- 0-100 score; tunable thresholds at top of file
    report.py              <- email Markdown body + Telegram short message
    adapters/
      polygon_options.py   <- Polygon.io chain snapshot fetcher
  flows/
    opex_risk.py           <- Prefect flow: opex_risk_pulse + opex_risk_weekly
  email.py                 <- SMTP sender (mirrors notify.py)

configs/
  fomc_meetings.yaml             <- FOMC dates 2025-2026 (update annually)
  bls_release_schedule.yaml      <- CPI + NFP dates 2025-2026 (update annually)

src/option_watch/
  chatWithGPT    <- original design rationale (GPT conversation)
  plan.md        <- full implementation plan
  README.md      <- user-facing setup + scheduling guide
```

### What still needs to happen before production

**Step 1 -- Pick a data provider and add credentials to `.env`** (see `.env.example`):

Three providers are supported via `OPTIONS_DATA_PROVIDER`:
- `ibkr` (recommended) -- live IV/Greeks/OI via IB Gateway, ~$1.50/mo OPRA subscription
- `polygon` -- paid HTTP API, ~$30+/mo
- `yfinance` -- free dev fallback (slow, no Greeks)

```
# IBKR (recommended) -- requires `uv sync --extra ibkr` + IB Gateway running + OPRA
OPTIONS_DATA_PROVIDER=ibkr
IBKR_HOST=127.0.0.1
IBKR_PORT=4001                   # gateway live; 4002 gateway paper, 7497 TWS paper
IBKR_CLIENT_ID=17
IBKR_MARKET_DATA_TYPE=1          # 1 live, 3 delayed (free)

# OR Polygon
POLYGON_API_KEY=...

# Email (required for weekly report)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...                # Gmail: use an app password
SMTP_FROM=...
SMTP_TO=...                      # comma-separated recipients
```

**Step 2 -- Smoke test** (no emails sent):
```bash
# IBKR: requires IB Gateway running and logged in
uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run --provider ibkr --underliers SPY

# Or full weekly dry-run with whatever provider is set in .env:
uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run
```

**Step 3 -- Provider notes**:
- IBKR: log into IB Gateway with the **live** account (market-data subscriptions are per live username); the adapter sets `readonly=True` on the connection so no orders can leak. SPX/NDX need the CBOE One add-on.
- Polygon: SPX/NDX require a higher tier; SPY/QQQ/SMH/SOXX work on most paid plans.
- yfinance: Greeks are estimated locally via Black-Scholes; OI for index ETFs is patchy. Use for dev only.

**Step 4 -- Register Prefect schedules** (Prefect server runs via `docker-compose up`):
```bash
# Wednesday full report 15:30 ET
prefect deployment build -n opex-weekly-wed hongquant/flows/opex_risk.py:opex_risk_weekly \
    --cron "30 15 * * 3" --timezone "America/New_York" && prefect deployment apply opex_risk_weekly-deployment.yaml

# Friday update 10:30 ET
prefect deployment build -n opex-weekly-fri hongquant/flows/opex_risk.py:opex_risk_weekly \
    --cron "30 10 * * 5" --timezone "America/New_York" && prefect deployment apply opex_risk_weekly-deployment.yaml

# Daily pulse Mon-Thu 08:00, 11:30, 15:30 ET
prefect deployment build -n opex-pulse hongquant/flows/opex_risk.py:opex_risk_pulse \
    --cron "0 8,11,15 * * 1-4" --timezone "America/New_York" && prefect deployment apply opex_risk_pulse-deployment.yaml
```

**Step 5 -- Update calendar YAMLs once per year:**
- `configs/fomc_meetings.yaml` from https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm
- `configs/bls_release_schedule.yaml` from https://www.bls.gov/schedule/news_release/

### Deferred to v0.3

- Backtest harness (false-positive / false-negative rate)
- Position-aware scoring (import actual portfolio holdings)
- Web dashboard
- Per-underlier alert threshold customization
- Tradier / IBKR fallback adapters

### Run tests

```bash
uv run pytest -q                           # all 52 tests
uv run pytest tests/test_options_*.py -v   # options tests only
uv run ruff check .                        # lint (currently clean)
```

### Risk score tuning

Threshold tables live at the top of `hongquant/options/risk_score.py`:
`_IV_PREMIUM_THRESHOLDS`, `_OI_BASELINE_THRESHOLDS`, `_VOL_OI_THRESHOLDS`, etc.
Edit these after a few weeks of live data to calibrate sensitivity.

---

## Suggested Resume Prompt

```
Read dev_conversation/resume_context.md, src/option_watch/plan.md, and src/option_watch/README.md.
The OpEx Momentum Risk Agent is fully implemented in hongquant/options/ (52 tests passing, ruff clean).
The immediate next task is [describe what you want to do].
```
