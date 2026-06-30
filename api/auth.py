import hashlib
import logging
import os
import time
from typing import Optional

logger = logging.getLogger(__name__)

_api_keys: dict[str, dict] = {}


def load_api_keys() -> None:
    raw = os.getenv("API_KEYS", "")
    if not raw:
        return
    for pair in raw.split(","):
        pair = pair.strip()
        if ":" in pair:
            key, name = pair.split(":", 1)
            _api_keys[key.strip()] = {
                "name": name.strip(),
                "created_at": time.time(),
            }
    logger.info("Loaded %d API keys", len(_api_keys))


def validate_api_key(key: Optional[str]) -> bool:
    if not key:
        return False
    if not _api_keys:
        load_api_keys()
    if not _api_keys:
        return True
    return key in _api_keys


def get_key_name(key: str) -> str:
    if key in _api_keys:
        return _api_keys[key]["name"]
    return "unknown"
