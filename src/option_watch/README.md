# OpEx Momentum Risk Agent

A scheduled market-risk monitoring agent that scans SPY / QQQ / SPX / NDX / SMH / SOXX options expiration structure, IV term structure, OI/gamma concentration, momentum fragility, and the macro event calendar — and sends a **weekly OpEx risk email every Wednesday** before US close.

## What it does

Every Wednesday at 15:30 ET, the agent:
1. Fetches the full options chain for each core underlier (via Polygon.io)
2. Computes front-week vs next-week ATM IV premium
3. Scans OI concentration, gamma walls (call wall / put wall), and volume/OI ratio
4. Measures QQQ/SPY and SMH/QQQ relative strength + watchlist breadth
5. Pulls VIX and checks for FOMC / CPI / NFP / OpEx events this week
6. Outputs a **0–100 Momentum Crash Risk Score** (Low / Medium / High / Extreme)
7. Sends a rich report by email + a brief Telegram pulse

**This is a risk radar — it does not generate buy/sell orders.**

## Where the code lives

All logic is in the main `hongquant` package:

```
hongquant/
├── options/
│   ├── adapters/polygon_options.py   # Polygon.io chain snapshot fetcher
│   ├── expiries.py                   # Front-Friday, monthly OpEx, triple witching helpers
│   ├── events.py                     # FOMC / CPI / NFP / earnings calendar
│   ├── metrics.py                    # ATM IV, OI, gamma exposure, max pain, etc.
│   ├── momentum.py                   # QQQ/SPY relative strength, breadth
│   ├── risk_score.py                 # 0-100 Momentum Crash Risk Score
│   ├── report.py                     # Email + Telegram body renderer
│   ├── store.py                      # Options snapshot Parquet store
│   └── types.py                      # Event, SnapshotBundle, RiskScore dataclasses
├── flows/opex_risk.py                # Prefect flow (pulse + weekly)
└── email.py                          # SMTP sender

configs/
├── fomc_meetings.yaml                # FOMC calendar (update annually)
└── bls_release_schedule.yaml         # CPI / NFP release dates (update annually)
```

## Setup

### 1. Add credentials to `.env`

```bash
# Polygon.io — options chain data
POLYGON_API_KEY=your_key_here

# Email delivery (Gmail app-password works)
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=you@gmail.com
SMTP_PASSWORD=app_password_here
SMTP_FROM=you@gmail.com
SMTP_TO=you@gmail.com

# Telegram (optional pulse channel)
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

### 2. Install dependencies

```bash
uv sync
```

### 3. Smoke test (no emails sent)

```bash
uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run
```

### 4. Seed historical baseline (optional, improves OI comparison signal)

After a few weeks of daily runs, the 12-week OI baseline auto-populates. For a faster start, run the pulse mode daily for a few weeks:

```bash
uv run python -m hongquant.flows.opex_risk --mode pulse
```

## Scheduling via Prefect

The Prefect server is provisioned in `docker-compose.yml`. Register schedules via the Prefect UI (`http://localhost:4200`) or CLI:

```bash
# Daily pulse (08:00, 11:30, 15:30 ET)
prefect deployment build -n opex-pulse hongquant/flows/opex_risk.py:opex_risk_pulse \
    --cron "0 8,11,15 * * 1-4" --timezone "America/New_York"

# Wednesday full report (15:30 ET)
prefect deployment build -n opex-weekly-wed hongquant/flows/opex_risk.py:opex_risk_weekly \
    --cron "30 15 * * 3" --timezone "America/New_York"

# Friday update (10:30 ET)
prefect deployment build -n opex-weekly-fri hongquant/flows/opex_risk.py:opex_risk_weekly \
    --cron "30 10 * * 5" --timezone "America/New_York"
```

## Risk Score

| Score | Band | Suggested posture |
| --- | --- | --- |
| 0–30 | Low | No action |
| 31–50 | Medium | Avoid new high-beta adds |
| 51–70 | High | Consider reducing 20–40% highest-beta exposure |
| 71–100 | Extreme | Do not chase; actively reduce crowded momentum |

Component weights: IV term structure (25) + OI/gamma concentration (25) + intraday flow (15) + momentum weakness (20) + event calendar (10) + VIX regime (5).

## Design rationale

See `chatWithGPT` in this directory — a full conversation that shaped the feature spec and signal selection.
