#!/bin/bash
# OpEx risk full weekly report — Wed + Fri
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.opex_risk --mode weekly 2>>logs/opex_risk.log
