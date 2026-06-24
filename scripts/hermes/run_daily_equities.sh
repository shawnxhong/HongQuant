#!/bin/bash
# Daily US equities OHLCV ingest — Mon-Fri post-16:30 ET
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.daily_equities 2>>logs/daily_equities.log
