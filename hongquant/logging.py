from __future__ import annotations

import sys
from functools import lru_cache

from loguru import logger

from .config import get_settings


@lru_cache(maxsize=1)
def setup_logging() -> None:
    settings = get_settings()
    logger.remove()
    logger.add(
        sys.stderr,
        level=settings.log_level,
        format=(
            "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
            "<level>{level: <8}</level> | "
            "<cyan>{name}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>"
        ),
    )


__all__ = ["logger", "setup_logging"]
