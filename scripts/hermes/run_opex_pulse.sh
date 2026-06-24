#!/bin/bash
# OpEx risk pulse scan — Mon/Tue/Thu intraday
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.opex_risk --mode pulse 2>>logs/opex_risk.log
