"""S3：实时行为推荐 —— 无 Kafka 时的进程内向后备（每主体一个有界滑窗）。

窗口只保留最近 `window_size` 条事件（`deque(maxlen=...)` 自动淘汰），主体数量也有界，
保证在没有任何外部服务、也没有持久存储的情况下内存可控。
"""
from __future__ import annotations

from collections import deque
from threading import Lock

from .event import BehaviorEvent

MAX_SUBJECTS = 10000


class InProcBus:
    def __init__(self, window_size: int):
        self.window_size = window_size
        self._lock = Lock()
        self._windows: dict[str, deque[BehaviorEvent]] = {}

    def publish(self, event: BehaviorEvent) -> tuple[BehaviorEvent, ...]:
        """写入事件并返回该主体最新的窗口快照（消费方按此快照决定是否产出推荐）。"""
        with self._lock:
            if event.subject_key not in self._windows and len(self._windows) >= MAX_SUBJECTS:
                del self._windows[next(iter(self._windows))]
            window = self._windows.setdefault(event.subject_key, deque(maxlen=self.window_size))
            window.append(event)
            return tuple(window)
