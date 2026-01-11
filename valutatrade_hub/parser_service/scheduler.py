from __future__ import annotations

import logging
import time

from valutatrade_hub.core.exceptions import ApiRequestError
from valutatrade_hub.parser_service.updater import RatesUpdater


def run_periodic(updater: RatesUpdater, interval_seconds: int) -> None:
    logger = logging.getLogger(__name__)
    logger.info("Scheduler started (interval=%ds)", interval_seconds)

    while True:
        try:
            updater.run_update()
        except ApiRequestError as e:
            logger.error("Update failed: %s", e)
        time.sleep(interval_seconds)
