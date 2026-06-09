"""Minimal Claude chat wrapper for the narrative layer.

Uses the official Anthropic SDK (`client.messages.create`). The model is
configurable via ``FRAGILITY_LLM_MODEL`` (defaults to the most capable Claude
model; set ``claude-haiku-4-5`` for the cheap path the design favors). Returns
``None`` and logs rather than raising whenever the LLM is disabled, unkeyed, or
errors — callers fall back to the deterministic report, so the radar never
depends on the LLM being available.
"""
from __future__ import annotations

from ..config import get_settings
from ..logging import logger, setup_logging


def is_enabled() -> bool:
    """True only if the narrative layer is turned on and usable."""
    s = get_settings()
    if not s.fragility_enable_llm:
        return False
    if s.fragility_llm_provider.lower() != "anthropic":
        logger.warning("LLM provider '{}' not wired; only 'anthropic' is supported", s.fragility_llm_provider)
        return False
    return bool(s.anthropic_api_key)


def complete(system: str, user: str, *, model: str | None = None, max_tokens: int = 2000) -> str | None:
    """Single-turn completion. Returns the text, or None if unavailable/errored."""
    setup_logging()
    s = get_settings()
    if not is_enabled():
        logger.info("LLM narrative disabled or no ANTHROPIC_API_KEY; skipping")
        return None
    try:
        import anthropic
    except ImportError:
        logger.warning("anthropic SDK not installed (run `uv sync`); skipping narrative")
        return None

    # Construction can also fail (proxy/transport/config) — guard it too so the
    # narrative never sinks the run.
    try:
        client = anthropic.Anthropic(api_key=s.anthropic_api_key)
        resp = client.messages.create(
            model=model or s.fragility_llm_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
    except anthropic.APIError as exc:
        logger.error("Claude API error: {}", exc)
        return None
    except Exception as exc:
        logger.error("LLM call failed: {}", exc)
        return None

    text = "".join(b.text for b in resp.content if getattr(b, "type", None) == "text")
    return text.strip() or None
