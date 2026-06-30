import logging
import random
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)


class RetryExhausted(Exception):
    def __init__(self, last_error: Exception, attempts: int):
        self.last_error = last_error
        self.attempts = attempts
        super().__init__(f"Retry exhausted after {attempts} attempts: {last_error}")


def retry(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential: float = 2.0,
    jitter: bool = True,
    retry_on: tuple = (Exception,),
    on_retry: Optional[Callable] = None,
):
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            return func()
        except retry_on as e:
            last_error = e
            if attempt == max_retries:
                break

            delay = min(base_delay * (exponential ** attempt), max_delay)
            if jitter:
                delay = delay * (0.5 + random.random() * 0.5)

            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs...",
                attempt + 1, max_retries + 1, str(e)[:100], delay,
            )

            if on_retry:
                on_retry(attempt + 1, e, delay)

            time.sleep(delay)

    raise RetryExhausted(last_error, max_retries + 1)


def retry_async(
    func: Callable,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential: float = 2.0,
    jitter: bool = True,
    retry_on: tuple = (Exception,),
):
    import asyncio

    async def wrapper():
        last_error = None
        for attempt in range(max_retries + 1):
            try:
                return await func()
            except retry_on as e:
                last_error = e
                if attempt == max_retries:
                    break
                delay = min(base_delay * (exponential ** attempt), max_delay)
                if jitter:
                    delay = delay * (0.5 + random.random() * 0.5)
                logger.warning("Async retry %d/%d: %s", attempt + 1, max_retries + 1, str(e)[:100])
                await asyncio.sleep(delay)
        raise RetryExhausted(last_error, max_retries + 1)

    return wrapper()
