"""LRM reaction-function LLM layer (advisory only).

The LLM analyses central-bank text and writes the monthly synthesis. It is
strictly advisory: it can dissent via ``analyst_dissent`` but never writes the
``quadrant`` field (spec §1.1, §5). Gated behind ``LRM_ENABLE_LLM`` (default
off) — the report renders fully without it.
"""
