"""EventBus — in-process pub/sub for job progress (SSE). Same interface a Redis Pub/Sub implementation will provide later:
publish(topic, event) · subscribe(topic) → iterator of events · history(topic) for late subscribers."""
from __future__ import annotations

import queue
import threading
import time
from collections import defaultdict, deque
from typing import Any, Iterator, Protocol


class EventBus(Protocol):
    def publish(self, topic: str, event: dict[str, Any]) -> None: ...
    def subscribe(self, topic: str, timeout: float = 30.0) -> Iterator[dict[str, Any]]: ...
    def history(self, topic: str) -> list[dict[str, Any]]: ...


class InProcessEventBus:
    def __init__(self, keep: int = 500):
        self._subs: dict[str, list[queue.Queue]] = defaultdict(list)
        self._hist: dict[str, deque] = defaultdict(lambda: deque(maxlen=keep))
        self._lock = threading.Lock()

    def publish(self, topic: str, event: dict[str, Any]) -> None:
        event = {**event, "ts": event.get("ts") or time.time()}
        with self._lock:
            self._hist[topic].append(event)
            subs = list(self._subs.get(topic, []))
        for q in subs:
            q.put(event)

    def subscribe(self, topic: str, timeout: float = 30.0) -> Iterator[dict[str, Any]]:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subs[topic].append(q)
            backlog = list(self._hist.get(topic, []))
        try:
            for e in backlog:
                yield e
            while True:
                try:
                    e = q.get(timeout=timeout)
                except queue.Empty:
                    yield {"type": "keepalive", "ts": time.time()}
                    continue
                yield e
                if e.get("type") in ("done", "failed", "cancelled"):
                    return
        finally:
            with self._lock:
                try:
                    self._subs[topic].remove(q)
                except ValueError:
                    pass

    def history(self, topic: str) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._hist.get(topic, []))


_default: EventBus | None = None


def get_event_bus() -> EventBus:
    """Factory: EVENT_BUS=inprocess (default). Future: redis (same interface)."""
    global _default
    if _default is None:
        _default = InProcessEventBus()
    return _default
