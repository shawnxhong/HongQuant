#!/bin/bash
# Fragility radar post-close scan — Mon-Fri
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.flows.fragility_radar 2>>logs/fragility_radar.log
