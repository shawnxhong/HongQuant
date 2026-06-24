#!/bin/bash
# Register HongQuant flows as Hermes cron jobs.
# Safe to re-run — existing jobs with the same name are removed first.
# All schedules in Beijing time (CST = UTC+8).
set -euo pipefail

PROJ=/home/hong/HongQuant
SCRIPTS=$PROJ/scripts/hermes

PROMPT_LIGHT='The script outputs a financial monitoring alert. Forward the full output to the user on Telegram and WeChat.'
PROMPT_FULL='The script outputs a financial monitoring report. Forward the full output to the user on Telegram and WeChat. If the output contains an [EMAIL | ...] section, also send the content of that section to the user via Email using the text after the pipe as the subject line.'

# Remove existing jobs to keep registration idempotent
for name in opex-pulse-0800 opex-pulse-1130 opex-pulse-1530 \
            opex-weekly-wed opex-weekly-fri \
            fragility-radar equity-pulse daily-equities \
            liquidity-daily liquidity-monthly; do
    hermes cron remove "$name" 2>/dev/null || true
done

# ── OpEx risk pulse ─────────────────────────────────────────────────────────
# Mon/Tue/Thu 08:00 ET → 20:00 BJT same day
hermes cron add "0 20 * * 1,2,4" \
  --name "opex-pulse-0800" \
  --script "$SCRIPTS/run_opex_pulse.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# Mon/Tue/Thu 11:30 ET → 23:30 BJT same day
hermes cron add "30 23 * * 1,2,4" \
  --name "opex-pulse-1130" \
  --script "$SCRIPTS/run_opex_pulse.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# Mon/Tue/Thu 15:30 ET → 03:30 BJT next day (Tue/Wed/Fri)
hermes cron add "30 3 * * 2,3,5" \
  --name "opex-pulse-1530" \
  --script "$SCRIPTS/run_opex_pulse.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# ── OpEx weekly report ───────────────────────────────────────────────────────
# Wed 15:30 ET → Thu 03:30 BJT
hermes cron add "30 3 * * 4" \
  --name "opex-weekly-wed" \
  --script "$SCRIPTS/run_opex_weekly.sh" \
  --workdir "$PROJ" \
  "$PROMPT_FULL"

# Fri 10:30 ET → Fri 22:30 BJT
hermes cron add "30 22 * * 5" \
  --name "opex-weekly-fri" \
  --script "$SCRIPTS/run_opex_weekly.sh" \
  --workdir "$PROJ" \
  "$PROMPT_FULL"

# ── Fragility radar (post-close) ─────────────────────────────────────────────
# Mon-Fri 17:00 ET → Tue-Sat 05:00 BJT
hermes cron add "0 5 * * 2-6" \
  --name "fragility-radar" \
  --script "$SCRIPTS/run_fragility_radar.sh" \
  --workdir "$PROJ" \
  "$PROMPT_FULL"

# ── Equity pulse (post-close) ────────────────────────────────────────────────
# Mon-Fri 17:15 ET → Tue-Sat 05:15 BJT
hermes cron add "15 5 * * 2-6" \
  --name "equity-pulse" \
  --script "$SCRIPTS/run_equity_pulse.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# ── Daily equities ingest ────────────────────────────────────────────────────
# Mon-Fri 16:45 ET → Tue-Sat 04:45 BJT (alerts only on failure)
hermes cron add "45 4 * * 2-6" \
  --name "daily-equities" \
  --script "$SCRIPTS/run_daily_equities.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# ── Liquidity regime daily ───────────────────────────────────────────────────
# Every day 07:00 BJT
hermes cron add "0 7 * * *" \
  --name "liquidity-daily" \
  --script "$SCRIPTS/run_liquidity_daily.sh" \
  --workdir "$PROJ" \
  "$PROMPT_LIGHT"

# ── Liquidity regime monthly ─────────────────────────────────────────────────
# Every Saturday 08:00 BJT; script self-guards for last-Saturday-only
hermes cron add "0 8 * * 6" \
  --name "liquidity-monthly" \
  --script "$SCRIPTS/run_liquidity_monthly.sh" \
  --workdir "$PROJ" \
  "$PROMPT_FULL"

echo "Registered 10 Hermes cron jobs. Current schedule:"
hermes cron list
