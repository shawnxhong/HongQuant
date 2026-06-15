"""LRM reaction-function runner — JSON-schema validation + retry + manual-TODO fallback.

Wraps the shared ``hongquant.llm.client.complete`` (does not modify it). Every
prompt is prefixed with the guardrail (spec §5): the model is an analyst, not a
decision-maker — it may dissent via ``analyst_dissent`` but must never write the
``quadrant`` field. JSON tasks are parsed and key-checked; on failure they retry
once, then fall back to a "manual TODO" record so a bad LLM response never sinks
the run. Gated behind ``LRM_ENABLE_LLM`` (default off).
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ...config import get_settings
from ...llm import client
from ...logging import logger

GUARDRAIL = (
    "你是数据分析师,不是决策者。你不得输出任何买卖建议,不得修改 quadrant 字段。"
    "如你的定性判断与机械状态机输出冲突,将异议写入 analyst_dissent 字段,陈述证据,不下指令。"
)

_PROMPT_DIR = Path(__file__).resolve().parent / "prompts"


def is_enabled() -> bool:
    """True only if the advisory layer is turned on and keyed."""
    s = get_settings()
    return bool(s.lrm_enable_llm and s.anthropic_api_key)


def load_prompt(name: str) -> str:
    """Load a prompt template by stem (e.g. ``p1_fomc_diff``)."""
    return (_PROMPT_DIR / f"{name}.md").read_text(encoding="utf-8")


def _extract_json(text: str) -> dict[str, Any] | None:
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                return None
    return None


def run_json_task(
    system_prompt: str,
    user_payload: str,
    *,
    required_keys: list[str],
    model: str | None = None,
    max_tokens: int = 1500,
) -> dict[str, Any]:
    """Run a strict-JSON task. Returns ``{"status": ok|disabled|manual_todo, ...}``."""
    if not is_enabled():
        return {"status": "disabled"}
    s = get_settings()
    system = (
        f"{GUARDRAIL}\n\n{system_prompt}\n\n"
        "Return ONLY a single valid JSON object — no prose, no markdown fences."
    )
    raw: str | None = None
    for attempt in (1, 2):
        raw = client.complete(system, user_payload, model=model or s.lrm_llm_model, max_tokens=max_tokens)
        if raw is None:
            return {"status": "manual_todo", "reason": "LLM unavailable"}
        parsed = _extract_json(raw)
        if parsed is not None and all(k in parsed for k in required_keys):
            return {"status": "ok", "data": parsed}
        logger.warning("LRM LLM task returned invalid/incomplete JSON (attempt {})", attempt)
    return {"status": "manual_todo", "reason": "invalid JSON after retry", "raw": raw}


def run_text_task(
    system_prompt: str,
    user_payload: str,
    *,
    model: str | None = None,
    max_tokens: int = 1200,
) -> str | None:
    """Run a free-text task (e.g. P4 monthly synthesis). Returns text or None."""
    if not is_enabled():
        return None
    s = get_settings()
    return client.complete(
        f"{GUARDRAIL}\n\n{system_prompt}",
        user_payload,
        model=model or s.lrm_llm_model,
        max_tokens=max_tokens,
    )
