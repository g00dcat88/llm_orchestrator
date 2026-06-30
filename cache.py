import hashlib
import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class ResponseCache:
    def __init__(self, db_path: str = "cache.db", ttl_seconds: int = 3600):
        self.db_path = Path(db_path)
        self.ttl_seconds = ttl_seconds
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    key TEXT PRIMARY KEY,
                    response TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.commit()

    def _make_key(self, prompt: str, system_prompt: str = "", tools: list = None) -> str:
        raw = json.dumps({
            "prompt": prompt,
            "system": system_prompt or "",
            "tools": [t.get("function", {}).get("name", "") for t in (tools or [])],
        }, sort_keys=True)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, prompt: str, system_prompt: str = "", tools: list = None) -> Optional[dict]:
        key = self._make_key(prompt, system_prompt, tools)
        with sqlite3.connect(str(self.db_path)) as conn:
            row = conn.execute(
                "SELECT response, created_at FROM cache WHERE key = ?", (key,)
            ).fetchone()
            if row:
                response_text, created_at = row
                if time.time() - created_at < self.ttl_seconds:
                    logger.debug("Cache hit for key=%s", key[:12])
                    return json.loads(response_text)
                else:
                    conn.execute("DELETE FROM cache WHERE key = ?", (key,))
                    conn.commit()
                    logger.debug("Cache expired for key=%s", key[:12])
        return None

    def set(self, prompt: str, response: dict, system_prompt: str = "", tools: list = None) -> None:
        key = self._make_key(prompt, system_prompt, tools)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO cache (key, response, created_at) VALUES (?, ?, ?)",
                (key, json.dumps(response, ensure_ascii=False), time.time()),
            )
            conn.commit()
        logger.debug("Cache stored for key=%s", key[:12])

    def clear(self) -> int:
        with sqlite3.connect(str(self.db_path)) as conn:
            count = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            conn.execute("DELETE FROM cache")
            conn.commit()
        logger.info("Cache cleared: %d entries", count)
        return count

    def cleanup_expired(self) -> int:
        cutoff = time.time() - self.ttl_seconds
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM cache WHERE created_at < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount

    def stats(self) -> dict:
        with sqlite3.connect(str(self.db_path)) as conn:
            total = conn.execute("SELECT COUNT(*) FROM cache").fetchone()[0]
            alive = conn.execute(
                "SELECT COUNT(*) FROM cache WHERE created_at > ?",
                (time.time() - self.ttl_seconds,),
            ).fetchone()[0]
        return {"total": total, "alive": alive, "expired": total - alive}
