from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from valutatrade_hub.infra.settings import SettingsLoader


def setup_logging() -> None:
    settings = SettingsLoader()
    log_path = Path(str(settings.get("LOG_PATH", "logs/actions.log")))
    log_path.parent.mkdir(parents=True, exist_ok=True)

    level_name = str(settings.get("LOG_LEVEL", "INFO")).upper()
    level = getattr(logging, level_name, logging.INFO)

    logger = logging.getLogger()
    logger.setLevel(level)

    # чтобы при повторном запуске не дублировались хендлеры
    if logger.handlers:
        return

    handler = RotatingFileHandler(
        log_path,
        maxBytes=512_000,
        backupCount=3,
        encoding="utf-8",
    )

    formatter = logging.Formatter(
        fmt="%(levelname)s %(asctime)s %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
