import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


class MetricsCollector:
    def __init__(self, db_path: str = "metrics.db"):
        self.db_path = Path(db_path)
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS metrics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp REAL NOT NULL,
                    metric_type TEXT NOT NULL,
                    name TEXT NOT NULL,
                    value REAL NOT NULL,
                    metadata TEXT
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_metrics_type_name
                ON metrics(metric_type, name)
            """)
            conn.commit()

    def record(self, metric_type: str, name: str, value: float, metadata: Optional[dict] = None) -> None:
        with self._lock:
            with sqlite3.connect(str(self.db_path)) as conn:
                conn.execute(
                    "INSERT INTO metrics (timestamp, metric_type, name, value, metadata) VALUES (?, ?, ?, ?, ?)",
                    (time.time(), metric_type, name, value, json.dumps(metadata) if metadata else None),
                )
                conn.commit()

    def record_timing(self, name: str, duration: float, **meta) -> None:
        self.record("timing", name, duration, meta)

    def record_counter(self, name: str, count: int = 1, **meta) -> None:
        self.record("counter", name, count, meta)

    def record_gauge(self, name: str, value: float, **meta) -> None:
        self.record("gauge", name, value, meta)

    def get_recent(self, metric_type: str, name: str, limit: int = 100) -> list[dict]:
        with sqlite3.connect(str(self.db_path)) as conn:
            rows = conn.execute(
                "SELECT timestamp, name, value, metadata FROM metrics WHERE metric_type = ? AND name = ? ORDER BY timestamp DESC LIMIT ?",
                (metric_type, name, limit),
            ).fetchall()
        return [
            {"timestamp": r[0], "name": r[1], "value": r[2], "metadata": json.loads(r[3]) if r[3] else None}
            for r in rows
        ]

    def get_summary(self, minutes: int = 60) -> dict:
        cutoff = time.time() - minutes * 60
        with sqlite3.connect(str(self.db_path)) as conn:
            timing_rows = conn.execute(
                "SELECT name, AVG(value), COUNT(*), MIN(value), MAX(value) FROM metrics WHERE metric_type = 'timing' AND timestamp > ? GROUP BY name",
                (cutoff,),
            ).fetchall()

            counter_rows = conn.execute(
                "SELECT name, SUM(value) FROM metrics WHERE metric_type = 'counter' AND timestamp > ? GROUP BY name",
                (cutoff,),
            ).fetchall()

        summary = {
            "period_minutes": minutes,
            "timings": {
                r[0]: {"avg_ms": round(r[1] * 1000, 2), "count": r[2], "min_ms": round(r[3] * 1000, 2), "max_ms": round(r[4] * 1000, 2)}
                for r in timing_rows
            },
            "counters": {r[0]: r[1] for r in counter_rows},
        }
        return summary

    def export_json(self) -> str:
        summary = self.get_summary(minutes=60)
        return json.dumps(summary, ensure_ascii=False, indent=2)

    def cleanup(self, days: int = 7) -> int:
        cutoff = time.time() - days * 86400
        with sqlite3.connect(str(self.db_path)) as conn:
            cursor = conn.execute("DELETE FROM metrics WHERE timestamp < ?", (cutoff,))
            conn.commit()
            return cursor.rowcount


class TimingContext:
    def __init__(self, collector: MetricsCollector, name: str, **meta):
        self.collector = collector
        self.name = name
        self.metadata = meta
        self.start: float = 0

    def __enter__(self):
        self.start = time.monotonic()
        return self

    def __exit__(self, *args):
        duration = time.monotonic() - self.start
        self.collector.record_timing(self.name, duration, **self.metadata)
