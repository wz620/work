"""S1：RRF 融合的只读 HTTP 入口。

复用既有 Provider 与 experiments.invoke 的错误映射；不写数据库（course_app 对
recommendation_results 无 INSERT），只把融合清单返回给调用方。
"""
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field

from recommender.contracts import Algorithm, RecommendationResult
from recommender.student.fusion import DEFAULT_SOURCES, PER_SOURCE, rrf_fuse
from .config import DATASET, SPLIT
from .errors import APIError
from .experiments import invoke
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["S1 多路召回RRF融合"])


class FusionRequest(Input):
    algorithm_sources: list[str] | None = Field(default=None, max_length=len(DEFAULT_SOURCES))
    limit: int | None = Field(default=None, ge=1, le=50)
    k: int | None = Field(default=None, ge=0, le=1000)
    weights: dict[str, float] | None = None


class FusionQuery(Input):
    limit: int | None = Field(default=None, ge=1, le=50)
    k: int | None = Field(default=None, ge=0, le=1000)


class FusionItem(Input):
    movie_id: str
    fusion_rank: int = Field(ge=1)
    score: float
    recall_sources: list[str]
    recall_ranks: dict[str, int]


class LegSummary(Input):
    source: str
    model_version: str
    count: int


class FusionResponse(Input):
    status: str = "ready"
    subject_key: str
    runtime_mode: str = "business"
    dataset_version: str
    split_version: str
    k: int
    sources: list[str]
    weights: dict[str, float]
    leg_summaries: list[LegSummary]
    generated_at: str
    items: list[FusionItem]


def _settings(request: Request):
    settings = request.app.state.settings
    if not settings.enable_fusion:
        raise APIError(503, "FUSION_DISABLED", "RRF 融合未启用")
    return settings


def _resolve_sources(names: list[str] | None, configured: list[str]) -> list[str]:
    resolved = list(configured) if names is None else list(names)
    if not resolved:
        raise APIError(422, "FUSION_SOURCES_EMPTY", "融合至少需要一个召回来源")
    seen, unknown = set(), []
    for name in resolved:
        if name in seen:
            continue
        seen.add(name)
        try:
            Algorithm(name)
        except ValueError:
            unknown.append(name)
    if unknown:
        raise APIError(422, "INVALID_FUSION_SOURCE", "召回来源必须是已定义的推荐算法", {"unknown": unknown})
    return [name for name in resolved if name in seen]


def _fuse(kind: str, uid: int, sources: list[str], limit: int, k: int,
          weights: dict[str, float] | None) -> FusionResponse:
    weight_map = {name: float((weights or {}).get(name, 1.0)) for name in sources}
    if weights:
        extra = sorted(set(weights) - set(sources))
        if extra:
            raise APIError(422, "INVALID_FUSION_WEIGHT", "权重键必须是本次召回来源", {"unknown": extra})
        if any(value < 0 for value in weight_map.values()):
            raise APIError(422, "INVALID_FUSION_WEIGHT", "权重不能为负数")
    rankings: dict[str, list[str]] = {}
    legs: dict[str, RecommendationResult] = {}
    for name in sources:
        result = invoke(Algorithm(name), kind, uid, PER_SOURCE)
        legs[name] = result
        rankings[name] = [item.movie_id for item in result.items]
    fused = rrf_fuse(rankings, k, weight_map)[:limit]
    return FusionResponse(
        subject_key=f"{kind}:{uid}", dataset_version=DATASET, split_version=SPLIT, k=k,
        sources=sources, weights=weight_map,
        leg_summaries=[LegSummary(source=name, model_version=legs[name].model_version,
                                 count=len(legs[name].items)) for name in sources],
        generated_at=datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z"),
        items=[FusionItem(movie_id=item.movie_id, fusion_rank=item.fusion_rank, score=item.score,
                          recall_sources=item.recall_sources, recall_ranks=item.recall_ranks)
               for item in fused])


@router.post("/fusion/recommendations", response_model=FusionResponse)
def my_fusion(payload: FusionRequest, request: Request, actor: ActorDependency):
    settings = _settings(request)
    sources = _resolve_sources(payload.algorithm_sources, settings.fusion_sources)
    limit = settings.fusion_limit if payload.limit is None else payload.limit
    k = settings.fusion_k if payload.k is None else payload.k
    return _fuse("app", actor.account_id, sources, limit, k, payload.weights)


@router.get("/demo/fusion/{ml_user_id}/recommendations", response_model=FusionResponse)
def history_fusion(ml_user_id: IdPath, request: Request,
                   query: Annotated[FusionQuery, Query()]):
    from sqlalchemy import text
    settings = _settings(request)
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    limit = settings.fusion_limit if query.limit is None else query.limit
    k = settings.fusion_k if query.k is None else query.k
    return _fuse("ml", uid, list(settings.fusion_sources), limit, k, None)
