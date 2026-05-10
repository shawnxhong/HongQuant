# OpEx Momentum Risk Agent — Implementation Plan

## Context

The user runs a personal mid-frequency quant book (~$600k, US equities + crypto, single operator) with a stated risk profile of "good drawdown control, not yet strongly profitable." They are exposed to high-beta / AI / semi / momentum names and want a defensive **risk radar** that surfaces — every Wednesday before US close — whether the upcoming Friday is a high-risk OpEx window so they can preemptively trim momentum exposure.

The companion ChatGPT brief at `src/option_watch/chatWithGPT` makes the case (which we accept) that the right framing is **"is the front-week IV abnormally pricing event risk + is OI/gamma concentrated at this Friday + is QQQ/SMH already losing relative strength?"** — *not* SPY/QQQ "expiration volume" alone, and *not* an order-generating system. Output is a 0–100 Momentum Crash Risk Score with a Low/Medium/High/Extreme band and the supporting evidence; the human still acts.

This sub-project is the **first feature work** after the Phase 0 data scaffold landed (commit `3590625`). It must reuse the existing pillars (`Settings`, `loguru`, `notify`, Prefect flows, Parquet+DuckDB store) and avoid building parallel infrastructure.

**Final plan resolutions (from clarifying questions):**
- **Layout**: lives in the canonical package — `hongquant/options/` + `hongquant/flows/opex_risk.py`. `src/option_watch/` keeps the spec + this plan; no runnable code there.
- **Data source**: **Polygon.io** options snapshot (one call per underlier returns IV / Greeks / OI / volume / quotes). Tradier and IBKR deferred.
- **Notifications**: **Telegram** (reuse `hongquant/notify.py`) for the daily pulse + **Email** (new `hongquant/email.py`, SMTP transport with Gmail app-password compatibility) for the rich Wednesday/Friday reports.
- **Scope**: ship MVP **v0.1 + v0.2** in one cut — full Momentum Crash Risk Score with gamma walls, IV rank, and 12-week historical baseline. Backtesting / dashboard / position-aware tuning deferred to v0.3.

---

## Architecture

```
hongquant/
├── options/                       (new package — empty placeholder today)
│   ├── __init__.py
│   ├── adapters/
│   │   ├── __init__.py
│   │   └── polygon_options.py     ← chain snapshot + previous-day OI fetch
│   ├── expiries.py                ← front-Friday, next-Friday, monthly/quarterly OpEx
│   ├── events.py                  ← FOMC / CPI / NFP / monthly OpEx calendar
│   ├── metrics.py                 ← ATM IV, term structure, OI/gamma by strike, max pain
│   ├── momentum.py                ← QQQ/SPY, SMH/QQQ relative strength, breadth
│   ├── risk_score.py              ← 0–100 score + Low/Med/High/Extreme band
│   ├── store.py                   ← options-snapshot Parquet schema + read/write
│   └── report.py                  ← Markdown body + Telegram-short body renderer
├── flows/
│   └── opex_risk.py               (new) Prefect flow w/ daily + Wed + Fri schedule
├── email.py                       (new) SMTP sender (mirrors notify.py shape)
├── config.py                      ← add SMTP_* fields
└── notify.py                      ← reused as-is for Telegram pulse

configs/
└── universe.yaml                  ← add `options_underliers` section

src/option_watch/
├── chatWithGPT                    ← keep as design rationale
├── README.md                      (new) one-pager: "what this is, where the code lives"
└── plan.md                        (new) copy of this implementation plan

tests/
├── test_options_expiries.py       (new)
├── test_options_metrics.py        (new)
├── test_options_risk_score.py     (new)
└── test_options_store.py          (new)

.env.example                       ← add SMTP_HOST/PORT/USER/PASSWORD/FROM/TO
```

**Architectural decision — options storage**: extend the existing Parquet+DuckDB lakehouse rather than introduce a new store. New partition convention:
```
{data_dir}/parquet/options/underlier={U}/snapshot_date={YYYY-MM-DD}/snapshot_{HHMMSS}.parquet
```
One row per (underlier, expiration, strike, type) per snapshot. Schema lives in `hongquant/options/store.py` and follows the same `Arrow schema + normalize/validate` pattern as `hongquant/data/schema.py`. Daily 15:30 ET snapshot is the canonical baseline used for the 12-week OI history.

---

## File-by-file implementation

### 1. `configs/universe.yaml` — extend
Add a new top-level key. Keeps lists of strings, matching existing convention:
```yaml
options_underliers:
  core_etfs:    [SPY, QQQ, SMH, SOXX]
  index:        [SPX, NDX]              # Polygon plan permitting
  vol:          [VIX]
momentum_watchlist:
  - NVDA
  - AVGO
  - AMD
  - MSFT
  - META
  - AMZN
  - GOOGL
  - TSLA
  - PLTR
  - ARM
  - ANET
  - CRWD
  - MSTR
```
Update `hongquant/universe.py` `Universe` dataclass with two new fields (`options_underliers: dict[str, list[str]]`, `momentum_watchlist: list[str]`) and extend `load_universe()` parsing.

### 2. `hongquant/config.py` — extend `Settings`
Add fields (all `str | None` defaults except port):
- `smtp_host`, `smtp_port: int = 587`, `smtp_user`, `smtp_password`, `smtp_from`, `smtp_to` (comma-separated list)
- `polygon_api_key` already exists — no change

### 3. `.env.example` — extend
Add a new SMTP block (Gmail app-password compatible):
```
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM=
SMTP_TO=
```

### 4. `hongquant/email.py` — new
Mirror the shape of `hongquant/notify.py`:
- `send_email(subject: str, body_markdown: str, *, body_html: str | None = None) -> bool`
- Uses `smtplib.SMTP` + `STARTTLS`, sends `multipart/alternative` (text + html). HTML rendered from markdown via `markdown` lib (light dep) or hand-rolled fallback.
- Lazy config check: if any SMTP_* is missing, log a warning and return `False` (no exception). Same graceful-degrade pattern as `notify.notify`.

### 5. `hongquant/options/adapters/polygon_options.py` — new
- `fetch_chain_snapshot(underlier: str, *, expirations: list[date] | None = None) -> pd.DataFrame`
  - Calls `GET /v3/snapshot/options/{underlier}` with pagination (`next_url`).
  - Returns one row per contract with columns: `underlier, expiration, strike, type, bid, ask, last, volume, open_interest, implied_volatility, delta, gamma, theta, vega, spot, snapshot_ts`.
  - Optional `expirations` filter applied client-side (Polygon's `expiration_date` query param works for one date at a time).
- `fetch_previous_day_oi(underlier: str) -> pd.DataFrame` — uses the same snapshot endpoint at end-of-day; OI on Polygon is updated overnight after OCC settlement, so the 08:00 ET pull is what populates the 12-week history.
- Uses `httpx.Client` + `tenacity` retry (3 attempts, exponential backoff) — both already in `pyproject.toml`.
- Reads `polygon_api_key` from `get_settings()`. Raises a clear `RuntimeError` if missing.

### 6. `hongquant/options/expiries.py` — new
Pure-Python date helpers, no I/O:
- `front_friday(today: date) -> date` — coming Friday (or today if Friday).
- `next_friday(today: date) -> date`
- `monthly_opex(year: int, month: int) -> date` — third Friday.
- `triple_witching(year: int, quarter: int) -> date` — third Friday of Mar/Jun/Sep/Dec.
- `expiries_within(today: date, days: int) -> list[date]` — Polygon snapshot helper.
- `is_opex_week(today: date) -> bool`.

### 7. `hongquant/options/events.py` — new
- `class EventCalendar` with `events_this_week(today: date) -> list[Event]`.
- Sources:
  - **FOMC** — hard-coded yearly schedule (8 meetings/yr, published a year ahead). Provide a small embedded YAML (`configs/fomc_meetings.yaml`) the user can update once a year.
  - **CPI / NFP / PPI** — BLS releases follow a stable monthly cadence; embed a small generator (BLS publishes the schedule as a fixed table). Same `configs/bls_release_schedule.yaml` approach.
  - **Earnings** — for v0.1+v0.2 limit to the momentum watchlist; query `yfinance.Ticker(...).calendar` (free, already a dep).
  - **Monthly OpEx / Triple Witching** — derived from `expiries.py`, no external source.
- Returns `Event(date, kind, label, importance)` records consumed by `risk_score.py` and `report.py`.

### 8. `hongquant/options/metrics.py` — new
Pure functions on a chain DataFrame. Critical to keep these I/O-free for testing.
- `atm_iv(chain, expiry, spot) -> float` — IV interpolated at the strike closest to spot (volume-weighted between the two nearest strikes if needed).
- `iv_term_structure(chain, spot) -> dict[date, float]` — ATM IV per expiry.
- `front_iv_premium(chain, spot) -> float` — `front_atm_iv / next_week_atm_iv - 1`.
- `total_oi(chain, expiry) -> dict` — `{call, put, total, put_call_ratio}`.
- `near_atm_oi(chain, expiry, spot, *, pct=0.02) -> int` — sum of OI within ±pct of spot.
- `volume_oi_ratio(chain, expiry) -> float`.
- `gamma_exposure_by_strike(chain, expiry, spot) -> pd.DataFrame` — `OI × 100 × gamma × spot² × 0.01` per strike, separated for calls and puts.
- `call_wall(...) -> float`, `put_wall(...) -> float` — strike with max call OI above spot / max put OI below spot.
- `max_pain(chain, expiry) -> float` — strike that minimizes total option-holder payoff.
- `expected_move(chain, expiry, spot) -> float` — ATM straddle price ÷ spot.
- `oi_vs_baseline(today_oi, history: pd.Series) -> float` — multiplier vs 12-week mean of equivalent-DTE Friday-expiry OI; baseline pulled from `store.py`.

### 9. `hongquant/options/momentum.py` — new
- `relative_strength(symbol_a, symbol_b, *, window=5, store) -> float` — pulls daily closes from the existing `hongquant.data.store` (DuckDB query over Parquet).
- `breadth(watchlist: list[str], store) -> dict` — `{pct_above_20dma, pct_above_50dma, advancers, decliners}`.
- `momentum_fragility_score(...) -> float` — composite 0–1 input to `risk_score.py`.

Reuses existing OHLCV data — no new fetcher needed for momentum.

### 10. `hongquant/options/risk_score.py` — new
- `compute_risk_score(snapshot: SnapshotBundle) -> RiskScore` returning `RiskScore(total: int, band: Literal["Low","Medium","High","Extreme"], components: dict[str, float], reasons: list[str])`.
- Component weights match the brief: IV term 25, OI/gamma concentration 25, intraday volume/flow 15, momentum weakness 20, event calendar 10, VIX regime 5.
- Each component is normalized 0–1 against documented thresholds (e.g. IV term: front_premium 0% → 0, 20% → 0.5, 35% → 0.85, 50%+ → 1.0). Threshold table lives at the top of the file with one-line comments — easy for the user to tune.
- `reasons` is the human-readable trigger list shown in the email body.

### 11. `hongquant/options/store.py` — new
- `OPTIONS_SNAPSHOT_SCHEMA` — `pyarrow` schema mirroring the Polygon adapter output.
- `write_snapshot(df, *, snapshot_ts) -> Path` — writes one Parquet file under `parquet/options/underlier=…/snapshot_date=…/snapshot_HHMMSS.parquet`.
- `read_snapshot(underlier, snapshot_date, ...) -> pd.DataFrame` — DuckDB glob query.
- `historical_friday_oi(underlier, *, weeks=12) -> pd.Series` — returns total Friday-expiry OI per past Friday from stored snapshots; used by `metrics.oi_vs_baseline`.

### 12. `hongquant/options/report.py` — new
- `render_email(score, snapshot_bundle, events) -> tuple[str, str]` — returns `(subject, markdown_body)` matching the brief's exact layout (risk level → conclusion → triggered signals → IV term table → OI/gamma table → momentum table → event calendar → suggested posture → top-3 watch tomorrow).
- `render_telegram(score) -> str` — short pulse: `[OpEx Risk: {band}] front IV +X%, Friday OI Yx avg, SMH {trend}`.
- Subject template exactly: `[OpEx Risk: {BAND}] {underlier} front IV {pct}, Friday OI {ratio}x avg, {momentum_signal}`.

### 13. `hongquant/flows/opex_risk.py` — new
Prefect flow + tasks, mirroring the structure of `flows/daily_equities.py`:
- `@task fetch_chains(underliers)` — calls Polygon adapter for each underlier (parallel via `.submit()`).
- `@task persist_snapshots(chains)` — writes Parquet via `options.store.write_snapshot`.
- `@task compute_metrics(chains)` — runs `metrics` module, returns a `SnapshotBundle`.
- `@task compute_score(bundle, events, momentum)` — calls `risk_score.compute_risk_score`.
- `@task deliver(score, bundle, *, channels)` — calls `email.send_email` and/or `notify.notify` based on `channels` arg.
- `@flow opex_risk_pulse(channels=["telegram"])` — light scan, runs at 08:00 / 11:30 / 15:30 ET daily.
- `@flow opex_risk_weekly(channels=["email","telegram"])` — full report, runs Wed 15:30 ET + Fri 10:30 ET.
- CLI: `uv run python -m hongquant.flows.opex_risk --mode {pulse,weekly} [--dry-run]`.
- Schedule registration done in Prefect UI/CLI separately (out of scope for code) — mention in `src/option_watch/README.md`.

### 14. `tests/` — new test files
All tests use `tmp_path` + `monkeypatch` to swap `Settings`, mirroring `test_store.py`:
- `test_options_expiries.py` — front_friday on Mon/Wed/Fri/Sat boundaries; monthly_opex matches known Fridays in 2025/2026; triple_witching for Mar 2026.
- `test_options_metrics.py` — fixture chain DataFrame, assert `atm_iv`, `front_iv_premium`, `gamma_exposure_by_strike`, `max_pain`, `call_wall/put_wall` on hand-computed values.
- `test_options_risk_score.py` — fabricated `SnapshotBundle` exercises each band (Low/Medium/High/Extreme) and verifies `reasons` mentions the dominant component.
- `test_options_store.py` — round-trip write/read; partition path correctness; `historical_friday_oi` returns expected series from a synthetic 12-week dataset.

### 15. `src/option_watch/README.md` + `plan.md` — new
- `README.md`: one page — "what is OpEx Risk Agent, where the code lives (`hongquant/options/`, `hongquant/flows/opex_risk.py`), how to run it (`uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run`), how to schedule via Prefect, link to chatWithGPT for design rationale."
- `plan.md`: copy of this file, so the plan stays under version control alongside the spec it executes.

---

## Daily / weekly schedule (timezone: America/New_York)

| Cron (ET) | Flow | Channels | Purpose |
| --- | --- | --- | --- |
| 08:00 daily | `opex_risk_pulse` | Telegram | Settle previous-day OI, refresh event calendar |
| 11:30 daily | `opex_risk_pulse` | Telegram | Mid-day IV / volume scan |
| 15:30 Mon/Tue/Thu | `opex_risk_pulse` | Telegram | Pre-close pulse (no email noise) |
| **15:30 Wed** | `opex_risk_weekly` | **Email + Telegram** | **Primary "should I trim Wednesday?" report** |
| 10:30 Fri | `opex_risk_weekly` | Email + Telegram | Same-day expiry pressure update |

Schedules are registered in Prefect (server already provisioned via `docker-compose.yml`); the flow code itself is schedule-agnostic so `--dry-run` is easy.

---

## Reused utilities (no need to rebuild)

| Concern | Existing module | How used |
| --- | --- | --- |
| Settings / API keys | `hongquant.config.get_settings()` | Polygon key, SMTP creds |
| Logging | `hongquant.logging.setup_logging() + logger` | First call in every task |
| Telegram alerts | `hongquant.notify.notify(text)` | Pulse channel |
| Prefect flow pattern | `hongquant/flows/daily_equities.py` | Template for `opex_risk.py` |
| Parquet schema pattern | `hongquant/data/schema.py` | Template for `options/store.py` |
| DuckDB read pattern | `hongquant/data/store.py::query()` | `historical_friday_oi`, momentum closes |
| OHLCV data | `hongquant.data.store` | Momentum / relative-strength inputs |
| VIX series | `hongquant.data.adapters.fred.fetch_series(["VIXCLS"])` | VIX regime input to risk score |
| Universe loader | `hongquant.universe.load_universe()` | Pulls `options_underliers`, `momentum_watchlist` |
| HTTP + retry | `httpx` + `tenacity` (already deps) | Polygon adapter |

---

## Verification

End-to-end smoke test once implemented:

1. **Unit tests** — `uv run pytest tests/test_options_*.py -q` passes; `ruff check .` clean.
2. **Adapter dry-run** — `uv run python -c "from hongquant.options.adapters.polygon_options import fetch_chain_snapshot; print(fetch_chain_snapshot('SPY').head())"` returns a populated DataFrame (requires `POLYGON_API_KEY` in `.env`).
3. **Flow dry-run, no delivery** — `uv run python -m hongquant.flows.opex_risk --mode weekly --dry-run` runs the full pipeline against live Polygon data, prints the rendered email body to stdout, persists a snapshot under `data/parquet/options/...`, but skips `send_email` / `notify`.
4. **Backfill 12-week baseline** — script (`scripts/backfill_options_oi.py`, optional) loops `fetch_previous_day_oi` for each underlier × past 60 trading days to seed `historical_friday_oi`. Without this, the `oi_vs_baseline` component returns "insufficient history" and contributes 0 to the score for the first ~12 weeks.
5. **Live delivery** — drop `--dry-run`; confirm Telegram message arrives via `notify` and SMTP email lands in inbox.
6. **Calendar sanity** — `uv run python -c "from hongquant.options.events import EventCalendar; print(EventCalendar().events_this_week(__import__('datetime').date.today()))"` shows this week's FOMC/CPI/earnings.
7. **Risk score sanity** — feed `compute_risk_score` a fabricated bundle reproducing the brief's "[OpEx Risk: HIGH] QQQ front IV +32%" example and assert it returns band `High`.

---

## Out of scope (deferred to v0.3)

- Backtest harness for false-positive / false-negative rate.
- Position-aware scoring (importing actual portfolio holdings).
- Web dashboard.
- Per-underlier alert threshold customization.
- Dealer-positioning inference beyond raw gamma concentration (the brief explicitly cautions against over-claiming dealer behavior — we follow that guidance).
- Tradier / IBKR fallback adapters (Polygon-only for v1).
