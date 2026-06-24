"""Alert output via stdout — consumed by the Hermes agent for dispatch."""
from __future__ import annotations


def notify(text: str) -> None:
    """Emit a short alert to stdout (Hermes routes to Telegram/WeChat)."""
    print(text)


def notify_email(subject: str, body_markdown: str) -> None:
    """Emit a full report to stdout, tagged so Hermes routes it via Email."""
    print(f"[EMAIL | {subject}]\n\n{body_markdown}")
