import logging
import threading
import time
from collections import defaultdict
from typing import Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    def __init__(self, rate: float, burst: int):
        self.rate = rate
        self.burst = burst
        self.tokens = float(burst)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self, n: int = 1) -> bool:
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last_refill = now

            if self.tokens >= n:
                self.tokens -= n
                return True
            return False

    @property
    def wait_time(self) -> float:
        if self.tokens >= 1:
            return 0.0
        return (1 - self.tokens) / self.rate


class RateLimiter:
    def __init__(self, rate: float = 10.0, burst: int = 20):
        self.rate = rate
        self.burst = burst
        self.buckets: dict[str, TokenBucket] = {}
        self._lock = threading.Lock()

    def _get_bucket(self, key: str) -> TokenBucket:
        with self._lock:
            if key not in self.buckets:
                self.buckets[key] = TokenBucket(self.rate, self.burst)
            return self.buckets[key]

    def allow(self, key: str = "default", cost: int = 1) -> bool:
        bucket = self._get_bucket(key)
        allowed = bucket.consume(cost)
        if not allowed:
            logger.warning("Rate limit exceeded for key=%s", key)
        return allowed

    def wait_and_allow(self, key: str = "default", cost: int = 1, timeout: float = 30.0) -> bool:
        bucket = self._get_bucket(key)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if bucket.consume(cost):
                return True
            wait = bucket.wait_time
            if wait > 0:
                time.sleep(min(wait, 0.1))
        logger.error("Rate limit timeout for key=%s", key)
        return False

    def get_wait_time(self, key: str = "default") -> float:
        bucket = self._get_bucket(key)
        return bucket.wait_time


class DualRateLimiter:
    def __init__(self, llm_rate: float = 5.0, llm_burst: int = 10, erp_rate: float = 20.0, erp_burst: int = 50):
        self.llm = RateLimiter(rate=llm_rate, burst=llm_burst)
        self.erp = RateLimiter(rate=erp_rate, burst=erp_burst)

    def allow_llm(self, key: str = "default") -> bool:
        return self.llm.allow(key)

    def allow_erp(self, key: str = "default") -> bool:
        return self.erp.allow(key)

    def wait_llm(self, key: str = "default", timeout: float = 30.0) -> bool:
        return self.llm.wait_and_allow(key, timeout=timeout)

    def wait_erp(self, key: str = "default", timeout: float = 10.0) -> bool:
        return self.erp.wait_and_allow(key, timeout=timeout)
