TASK P3 — BoJ / PBoC scan (spec §5.3, quarterly or event-triggered).

You are given central-bank text for either the Bank of Japan (statement +
governor press-conference points) or the People's Bank of China (quarterly
monetary-policy report + any rate/RRR change). Summarize the policy stance and
its carry / credit-impulse implication. Reference only the provided text.

Output a single JSON object. For BoJ:

{
  "bank": "BoJ",
  "policy_shift": <true|false>,
  "carry_implication": "tightening|easing|neutral",
  "note_zh": "<≤120字中文>"
}

For PBoC:

{
  "bank": "PBoC",
  "stance_shift": "tightening|easing|neutral",
  "credit_impulse_outlook": "up|down|flat",
  "note_zh": "<≤120字中文>"
}

INPUT:
{context}
