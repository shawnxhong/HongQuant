#!/bin/bash
# Liquidity regime daily interrupt check — every day at 07:00 BJT
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.liquidity_monitor --mode daily 2>>logs/liquidity_monitor.log
