from __future__ import annotations

import functools
import logging
from datetime import datetime
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def log_action(action: str, verbose: bool = False) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            ts = datetime.now().replace(microsecond=0).isoformat()
            logger = logging.getLogger(__name__)

            try:
                result = func(*args, **kwargs)
                # Пытаемся вытащить контекст из результата (если это dict)
                context = ""
                if verbose and isinstance(result, dict):
                    before = result.get("before")
                    after = result.get("after")
                    if before is not None and after is not None:
                        context = f" before={before} after={after}"

                logger.info(f"{ts} {action} result=OK kwargs={kwargs}{context}")
                return result
            except Exception as e:
                logger.info(
                    f"{ts} {action} result=ERROR error_type={type(e).__name__} error_message={e} kwargs={kwargs}"
                )
                raise

        return wrapper

    return decorator