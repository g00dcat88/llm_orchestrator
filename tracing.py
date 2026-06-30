import json
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Optional

logger = logging.getLogger(__name__)

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")
_spans: ContextVar[list[dict]] = ContextVar("spans", default=[])


def new_trace_id() -> str:
    return uuid.uuid4().hex[:16]


def get_trace_id() -> str:
    tid = _trace_id.get()
    if not tid:
        tid = new_trace_id()
        _trace_id.set(tid)
    return tid


def start_span(name: str, attributes: Optional[dict] = None) -> dict:
    span = {
        "trace_id": get_trace_id(),
        "span_id": uuid.uuid4().hex[:8],
        "name": name,
        "start_time": time.time(),
        "end_time": None,
        "duration_ms": None,
        "status": "ok",
        "attributes": attributes or {},
    }
    spans = _spans.get()
    spans.append(span)
    _spans.set(spans)
    return span


def end_span(span: dict, status: str = "ok", error: Optional[str] = None) -> None:
    span["end_time"] = time.time()
    span["duration_ms"] = round((span["end_time"] - span["start_time"]) * 1000, 2)
    span["status"] = status
    if error:
        span["error"] = error


def get_spans() -> list[dict]:
    return list(_spans.get())


def reset_trace() -> None:
    _trace_id.set(new_trace_id())
    _spans.set([])


class SpanContext:
    def __init__(self, name: str, **attributes):
        self.name = name
        self.attributes = attributes
        self.span: Optional[dict] = None

    def __enter__(self):
        self.span = start_span(self.name, self.attributes)
        return self.span

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.span:
            if exc_type:
                end_span(self.span, status="error", error=str(exc_val))
            else:
                end_span(self.span)


def format_trace(spans: Optional[list[dict]] = None) -> str:
    if spans is None:
        spans = get_spans()
    if not spans:
        return "No trace data"

    lines = [f"Trace: {spans[0]['trace_id']}"]
    for s in spans:
        status = "OK" if s["status"] == "ok" else "ERR"
        duration = f"{s['duration_ms']:.1f}ms" if s["duration_ms"] else "..."
        lines.append(f"  [{status}] {s['name']} — {duration}")
        if s.get("error"):
            lines.append(f"         Error: {s['error']}")
    return "\n".join(lines)
