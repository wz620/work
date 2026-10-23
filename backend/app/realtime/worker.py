"""S3：实时行为推荐 —— 消费逻辑与（可选）Kafka 工作线程。

`consume()` 是唯一的消费入口：离线演示端点经 `InProcBus` 直接调用它，Kafka 模式只把
"事件来源"换成真实 topic，之后仍调用同一方法，因此两条链路行为一致。

产出只进进程内缓存（`course_app` 对 `recommendation_results` 无 INSERT 授权，不落库）；
窗口事件数不足 `COLD_START_THRESHOLD` 时降级到冷启动算法，并在结果里如实标注。
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import logging
from threading import Event, Lock, Thread

from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, recommend
from recommender.data import ContractError

from ..config import DATASET, SPLIT
from ..errors import APIError
from .bus import InProcBus
from .event import BehaviorEvent, parse
from .kafka_adapter import AdapterUnavailable, consumer as kafka_consumer

log = logging.getLogger("course_api")
COLD_START_THRESHOLD = 3
POLL_TIMEOUT_MS = 1000


@dataclass(frozen=True)
class RealtimeRecommendation:
    subject_key: str
    algorithm: str
    degraded: bool
    window_size: int
    batch_token: str
    generated_at: str
    status: str = "ready"
    model_version: str | None = None
    error: str | None = None
    items: list[dict] = field(default_factory=list)

    def as_payload(self) -> dict:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def batch_token(subject_key: str, last_event_id: str, algorithm: str) -> str:
    """确定性批次标识：同一主体在"相同末事件 + 相同算法"下不重复产出。"""
    digest = hashlib.sha256(f"{subject_key}|{last_event_id}|{algorithm}".encode("utf-8"))
    return digest.hexdigest()


class RealtimeWorker(Thread):
    def __init__(self, settings):
        super().__init__(name="cinelab-realtime", daemon=True)
        self.settings = settings
        self.bus = InProcBus(settings.realtime_window_events)
        self._lock = Lock()
        self._cache: dict[str, RealtimeRecommendation] = {}
        self._stopped = Event()

    # ---- 离线端点与 Kafka 共用的消费逻辑 ---------------------------------------
    def consume(self, event: BehaviorEvent, preferred_algorithm: str | None = None) -> RealtimeRecommendation:
        # 注意：rate / favorite 事件的 DB 写入已由 router._write_event_to_db 在调用前完成，
        # 那里用的是 request.app.state.db（跟 recommend() 的 read_history 同一个实例）。
        # 这里只负责 InProcBus 窗口滑窗 + 推荐计算。

        window = self.bus.publish(event)
        degraded = len(window) < COLD_START_THRESHOLD
        if degraded:
            algorithm = self.settings.realtime_cold_start_algorithm
        elif preferred_algorithm:
            algorithm = preferred_algorithm
        else:
            algorithm = self.settings.realtime_algorithm
        token = batch_token(event.subject_key, event.event_id, algorithm)
        with self._lock:
            cached = self._cache.get(event.subject_key)
            if cached is not None and cached.batch_token == token:
                return cached
        record = self._recommend(event, len(window), algorithm, degraded, token)
        with self._lock:
            self._cache[event.subject_key] = record
        return record

    def _sync_event_to_db(self, event: BehaviorEvent) -> None:
        """把 rate / favorite 事件落到 account_ratings / account_favorites。
        view 事件不写库（account_views 不存在，也不会影响 ALS 计算）。"""
        try:
            from sqlalchemy import text
            from backend.app.config import ROOT, Settings
            from backend.app.db import Database
            import os
            # 复用主进程相同的 Settings（读同一套 secrets / env）
            if not hasattr(self, "_db"):
                settings = Settings(_env_file=os.getenv("APP_ENV_FILE", str(ROOT / "backend/.env")))
                self._db = Database(settings)
            mid = int(event.movie_id)
            aid = event.subject_id
            with self._db.connection(write=True) as conn:
                if event.event_type == "rate" and event.rating:
                    conn.execute(text(
                        "INSERT INTO account_ratings (account_id, movie_id, rating) "
                        "VALUES (:aid, :mid, CAST(:rating AS DECIMAL(3,1))) "
                        "ON DUPLICATE KEY UPDATE rating=VALUES(rating), updated_at=NOW(6)"
                    ), {"aid": aid, "mid": mid, "rating": event.rating})
                elif event.event_type == "favorite":
                    conn.execute(text(
                        "INSERT IGNORE INTO account_favorites (account_id, movie_id) VALUES (:aid, :mid)"
                    ), {"aid": aid, "mid": mid})
        except Exception as exc:
            # 实时写入是"尽力而为"；失败不阻塞推荐主链路
            log.warning("实时事件写库失败 event=%s reason=%s", event.event_id, exc)

    def cached(self, subject_key: str) -> RealtimeRecommendation | None:
        with self._lock:
            return self._cache.get(subject_key)

    def _recommend(self, event: BehaviorEvent, window_size: int, algorithm: str,
                   degraded: bool, token: str) -> RealtimeRecommendation:
        request = RecommendationRequest(event.subject_kind, event.subject_id, self.settings.realtime_limit,
                                        "business", DATASET, SPLIT)
        try:
            result = recommend(Algorithm(algorithm), request)
        except AlgorithmNotImplemented as exc:
            return RealtimeRecommendation(event.subject_key, algorithm, degraded, window_size, token, _utc_now(),
                                          status="unavailable", error="ALGORITHM_NOT_IMPLEMENTED: " + exc.args[0])
        except ContractError as exc:
            return RealtimeRecommendation(event.subject_key, algorithm, degraded, window_size, token, _utc_now(),
                                          status="unavailable", error=exc.code)
        return RealtimeRecommendation(
            event.subject_key, algorithm, degraded, window_size, token, _utc_now(),
            model_version=result.model_version,
            items=[{"movie_id": item.movie_id, "rank": item.rank, "score": item.score} for item in result.items])

    # ---- 仅 Kafka 模式使用的来源替换 -------------------------------------------
    def run(self) -> None:
        try:
            stream = kafka_consumer(self.settings.kafka_bootstrap, self.settings.kafka_topic,
                                    self.settings.kafka_group)
        except Exception as exc:
            log.error("实时消费者不可用，事件来源保持进程内总线；reason=%s",
                      exc if isinstance(exc, AdapterUnavailable) else type(exc).__name__)
            return
        log.info("实时消费者已启动 topic=%s group=%s", self.settings.kafka_topic, self.settings.kafka_group)
        while not self._stopped.is_set():
            for messages in stream.poll(timeout_ms=POLL_TIMEOUT_MS).values():
                for message in messages:
                    try:
                        self.consume(parse(message.value))
                    except APIError as exc:
                        log.warning("丢弃非法实时事件 code=%s", exc.code)
            stream.commit()

    def stop(self) -> None:
        self._stopped.set()
