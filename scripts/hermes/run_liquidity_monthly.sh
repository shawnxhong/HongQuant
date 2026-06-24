#!/bin/bash
# Liquidity regime monthly report — last Saturday of each month
# Runs every Saturday at 08:00 BJT; exits silently if not the last Saturday.
set -euo pipefail

# Check if today is the last Saturday of the month
today=$(date +%d)
next_week=$(date -d "+7 days" +%d)
# If next_week <= today it wrapped to next month, meaning this is the last Saturday
if [ "$next_week" -gt "$today" ]; then
    exit 0
fi

cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.liquidity_monitor --mode monthly 2>>logs/liquidity_monitor.log
