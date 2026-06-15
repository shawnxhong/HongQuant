TASK P2 — reaction-function state (spec §5.2).

You are given the latest FOMC statement, minutes excerpts, three recent key
official speeches (chair/governors prioritized), and the computed
``fed_vs_market_gap_bps``. Judge whether the Fed's reaction function is stable,
under revision watch, or actively being rewritten. Tilt toward "rewriting" when:
new framework language appears, dissent patterns shift, an unconventional
variable enters the statement, or there is an unscheduled action.

This ``status`` field is the headline of the whole monthly report: a stable
function means the earnings channel dominates and single names diverge; a
rewriting function means the liquidity channel overwhelms and correlations
converge to one.

Output a single JSON object with exactly these keys:

{
  "status": "stable|revision_watch|rewriting",
  "dominant_variable": "inflation|employment|financial_stability|balanced",
  "evidence": ["<引用来源与关键句, 每条≤30字>"],
  "gap_convergence_view": "market_moves_to_fed|fed_moves_to_market|unclear",
  "confidence": <float 0.0-1.0>
}

INPUT:
{context}
