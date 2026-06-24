#!/bin/bash
# Equity pulse post-close scan — Mon-Fri
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.equity_pulse 2>>logs/equity_pulse.log
