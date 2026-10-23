"""S3：实时行为推荐 —— 事件 schema 与解析。

事件是最小的不可变事实：谁（subject）对哪部电影（movie_id）做了什么（event_type）。
既不写数据库也不写持久文件；事件只经进程内总线或 Kafka 流入同一段消费逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Literal
from uuid import uuid4

from pydantic import Field, ValidationError, field_validator, model_validator

from ..errors import APIError
from ..schemas import Input


@dataclass(frozen=True)
class BehaviorEvent:
    event_id: str
    subject_kind: str
    subject_id: int
    movie_id: str
    event_type: str
    rating: str | None
    occurred_at: str

    @property
    def subject_key(self) -> str:
        return f"{self.subject_kind}:{self.subject_id}"

    def as_payload(self) -> dict:
        return {"event_id": self.event_id, "subject_kind": self.subject_kind, "subject_id": str(self.subject_id),
                "subject_key": self.subject_key, "movie_id": self.movie_id, "event_type": self.event_type,
                "rating": self.rating, "occurred_at": self.occurred_at}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class EventPayload(Input):
    """事件入参：离线演示端点与 Kafka 消息共用同一份校验。"""

    subject_kind: Literal["app", "ml"] = "app"
    subject_id: int | None = Field(default=None, ge=1, le=2**64 - 1)
    movie_id: str = Field(pattern=r"^[1-9][0-9]{0,19}$")
    event_type: Literal["view", "rate", "favorite"]
    rating: Decimal | None = None
    event_id: str | None = Field(default=None, min_length=1, max_length=64)
    occurred_at: str | None = Field(default=None, min_length=1, max_length=40)
    # 前端可选指定实时算法（覆盖 settings.realtime_algorithm），方便演示切换
    preferred_algorithm: str | None = Field(default=None, min_length=2, max_length=32)

    @field_validator("occurred_at")
    @classmethod
    def iso_utc(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.endswith("Z"):
            raise ValueError("occurred_at 必须是 UTC（以 Z 结尾）的 ISO-8601 时间")
        try:
            datetime.fromisoformat(value[:-1] + "+00:00")
        except ValueError:
            raise ValueError("occurred_at 不是合法 ISO-8601 时间") from None
        return value

    @model_validator(mode="after")
    def rating_matches_type(self) -> "EventPayload":
        if self.event_type != "rate":
            if self.rating is not None:
                raise ValueError("只有 rate 事件可以携带 rating")
            return self
        if self.rating is None:
            raise ValueError("rate 事件必须携带 rating")
        try:
            number = Decimal(str(self.rating))
        except InvalidOperation:
            raise ValueError("评分无效") from None
        if (not number.is_finite() or not Decimal("0.5") <= number <= Decimal("5.0")
                or number * 2 != (number * 2).to_integral_value()):
            raise ValueError("评分范围为0.5到5.0，步长0.5")
        return self

    def to_event(self, subject_id: int | None = None) -> BehaviorEvent:
        resolved = subject_id if subject_id is not None else self.subject_id
        if resolved is None:
            raise APIError(422, "INVALID_REALTIME_EVENT", "必须提供事件主体 subject_id")
        return BehaviorEvent(
            event_id=self.event_id or uuid4().hex, subject_kind=self.subject_kind, subject_id=resolved,
            movie_id=self.movie_id, event_type=self.event_type,
            rating=None if self.rating is None else f"{Decimal(str(self.rating)):.1f}",
            occurred_at=self.occurred_at or _utc_now())


def parse(message: dict, default_subject_id: int | None = None) -> BehaviorEvent:
    """解析来自 Kafka 的原始事件体；结构不合法一律 422，不静默丢弃成"未知事件"。"""
    try:
        payload = EventPayload.model_validate(message)
    except ValidationError as exc:
        details = [{"location": list(item["loc"]), "type": item["type"]} for item in exc.errors()]
        raise APIError(422, "INVALID_REALTIME_EVENT", "实时事件结构不合法", details) from None
    return payload.to_event(default_subject_id)
