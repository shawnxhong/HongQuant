"""Telegram notifications via the Bot HTTP API. No-ops when token absent."""
from __future__ import annotations

import httpx

from .config import get_settings
from .logging import logger, setup_logging


def notify(text: str) -> None:
    """Send a Telegram message. Safe to call anywhere; logs and returns on error."""
    setup_logging()
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_chat_id:
        logger.warning("Telegram not configured; dropping: {}", text[:200])
        return
    url = f"https://api.telegram.org/bot{settings.telegram_bot_token}/sendMessage"
    try:
        httpx.post(
            url,
            data={
                "chat_id": settings.telegram_chat_id,
                "text": text,
                "parse_mode": "Markdown",
            },
            timeout=10.0,
        ).raise_for_status()
    except httpx.HTTPError as exc:
        logger.error("Telegram send failed: {}", exc)
