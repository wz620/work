"""S3：实时行为推荐的只读 HTTP 入口。

`POST /demo/realtime/events` 是离线可验的事件入口：身份取自会话（app 主体的
`subject_id` 一律以会话账号为准，ml 主体需为真实历史匿名用户），事件经进程内总线
进入 `RealtimeWorker.consume()`，与 Kafka 模式完全同一段消费逻辑。
`GET /me/realtime/recommendations` 读进程内缓存；结果不落库。
"""
from __future__ import annotations

from fastapi import APIRouter, Request
from sqlalchemy import text

from ..errors import APIError
from ..schemas import Input
from ..security import ActorDependency
from .event import EventPayload

router = APIRouter(tags=["S3 Kafka 实时行为推荐"])


def _write_event_to_db(db, event) -> None:
    """把 rate / favorite 事件落到 account_ratings / account_favorites。
    必须用 app 同一个 db 实例（request.app.state.db），否则 MySQL REPEATABLE READ
    隔离下新写入对后续 recommend() 的 read_history() 不可见。"""
    try:
        mid = int(event.movie_id)
        aid = event.subject_id
        with db.connection(write=True) as conn:
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
        # 尽力而为；失败不阻塞推荐主链路
        import logging
        logging.getLogger("course_api").warning("实时事件写库失败 event=%s reason=%s", event.event_id, exc)


class RealtimeResponse(Input):
    subject_key: str
    algorithm: str
    degraded: bool
    window_size: int
    batch_token: str
    generated_at: str
    status: str
    model_version: str | None = None
    error: str | None = None
    items: list[dict]


class EventAccepted(Input):
    status: str = "accepted"
    event: dict
    recommendation: RealtimeResponse


def _worker(request: Request):
    settings = request.app.state.settings
    worker = getattr(request.app.state, "realtime", None)
    if not settings.enable_realtime or worker is None:
        raise APIError(503, "REALTIME_DISABLED", "实时行为推荐未启用")
    return settings, worker


@router.post("/demo/realtime/events", response_model=EventAccepted)
def publish_event(payload: EventPayload, request: Request, actor: ActorDependency):
    _, worker = _worker(request)
    if payload.subject_kind == "app":
        # 身份只信会话：app 事件不接受调用方指定他人的账号。
        if payload.subject_id is not None and payload.subject_id != actor.account_id:
            raise APIError(403, "SUBJECT_MISMATCH", "app 事件的 subject_id 必须与会话账号一致")
        subject_id = actor.account_id
    else:
        if payload.subject_id is None:
            raise APIError(422, "INVALID_REALTIME_EVENT", "ml 事件必须提供 subject_id")
        subject_id = payload.subject_id
        with request.app.state.db.connection() as conn:
            if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"),
                            {"id": subject_id}).first() is None:
                raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    event = payload.to_event(subject_id)
    # 先把 rate / favorite 事件同步写 DB（用 app 同一个 db 实例），
    # 保证后续 recommend() 读历史时能看到新行为。
    if event.subject_kind == "app":
        _write_event_to_db(request.app.state.db, event)
    record = worker.consume(event, preferred_algorithm=payload.preferred_algorithm)
    return EventAccepted(event=event.as_payload(), recommendation=RealtimeResponse(**record.as_payload()))


@router.get("/me/realtime/recommendations", response_model=RealtimeResponse)
def my_realtime_recommendations(request: Request, actor: ActorDependency):
    _, worker = _worker(request)
    record = worker.cached("app:" + str(actor.account_id))
    if record is None:
        raise APIError(404, "REALTIME_RESULT_NOT_READY", "尚无实时行为事件，推荐结果未产出")
    return RealtimeResponse(**record.as_payload())
