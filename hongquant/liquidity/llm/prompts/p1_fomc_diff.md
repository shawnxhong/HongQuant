TASK P1 — FOMC statement diff (spec §5.1).

You are given the full text of the latest FOMC statement and the previous one.
Identify every substantive change, classify each as hawkish/dovish/neutral, and
attribute it to a mandate variable. Reference only the provided text; do not
recall figures from memory.

Output a single JSON object with exactly these keys:

{
  "changes": [
    {"old": "...", "new": "...",
     "classification": "hawkish|dovish|neutral",
     "mandate_variable": "inflation|employment|financial_stability|other"}
  ],
  "hawk_dove_score": <integer -5..+5>,
  "financial_conditions_mention_count": <integer>,
  "summary_zh": "<≤120字中文>"
}

INPUT:
{context}
