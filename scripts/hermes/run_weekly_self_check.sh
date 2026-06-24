#!/bin/bash
# Weekly external dependency self-check
set -euo pipefail
cd /home/hong/HongQuant
mkdir -p logs
uv run python -m hongquant.diagnostics.weekly_self_check 2>>logs/weekly_self_check.log
