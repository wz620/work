from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import Field
from sqlalchemy import text

from recommender.contracts import Algorithm, AlgorithmNotImplemented, RecommendationRequest, RecommendationResult, PROVIDERS, recommend
from recommender.data import ContractError
from .config import DATASET, SPLIT
from .errors import APIError
from .schemas import IdPath, Input, identifier
from .security import ActorDependency

router = APIRouter(tags=["学生算法预留边界"])


class RecommendationQuery(Input):
    # HTTP 客户端常带 ?__t=ts 之类的 cache-bust 参数；基础 Input 要求 extra=forbid，
    # 这里覆盖为 allow，让推荐端点对这类无害噪声保持健壮。
    model_config = {"extra": "allow"}
    limit: int = Field(default=10, ge=1, le=50)


def invoke(algorithm: Algorithm, kind: str, uid: int, limit: int):
    request = RecommendationRequest(kind, uid, limit, "business", DATASET, SPLIT)
    try:
        return recommend(algorithm, request)
    except AlgorithmNotImplemented:
        raise APIError(501, "ALGORITHM_NOT_IMPLEMENTED", "此推荐算法留给学生实现", {
            "status": "not_implemented", "algorithm": algorithm.value, "subject_key": kind + ":" + str(uid),
            "dataset_version": DATASET, "split_version": SPLIT, "runtime_mode": "business",
            "model_version": None, "batch_id": None, "items": []}) from None
    except ContractError as exc:
        raise APIError(503 if exc.code in {"MODEL_BINDING_INVALID", "DATA_IDENTITY_INVALID", "DATA_MODE_INVALID"} else 500,
            exc.code, str(exc)) from None


@router.get("/experiments/algorithms")
def algorithms():
    return {"items": [{"algorithm": algorithm.value, "status": "registered" if algorithm in PROVIDERS else "not_implemented"} for algorithm in Algorithm]}


@router.get("/experiments/evaluations")
def evaluations():
    raise APIError(501, "EVALUATION_NOT_IMPLEMENTED", "评价流程留给学生实现；业务API不连接evaluation数据库", {
        "status": "not_implemented", "metrics": None, "dataset_version": DATASET, "split_version": SPLIT})


@router.get("/me/recommendations/{algorithm}", response_model=RecommendationResult)
def my_recommendations(algorithm: Algorithm, actor: ActorDependency, query: Annotated[RecommendationQuery, Query()]):
    return invoke(algorithm, "app", actor.account_id, query.limit)


@router.get("/demo/history-users/{ml_user_id}/recommendations/{algorithm}", response_model=RecommendationResult)
def history_recommendations(ml_user_id: IdPath, algorithm: Algorithm, request: Request,
                            query: Annotated[RecommendationQuery, Query()]):
    uid = identifier(ml_user_id)
    with request.app.state.db.connection() as conn:
        if conn.execute(text("SELECT ml_user_id FROM history_users WHERE ml_user_id=:id"), {"id": uid}).first() is None:
            raise APIError(404, "HISTORY_USER_NOT_FOUND", "历史匿名用户不存在")
    return invoke(algorithm, "ml", uid, query.limit)


@router.get("/public/recommendations/{algorithm}", response_model=RecommendationResult)
def public_recommendations(algorithm: Algorithm, query: Annotated[RecommendationQuery, Query()]):
    """匿名用户公共推荐：仅支持 popular（不依赖历史评分）。
    绕过 invoke 内部的 business.read_history uid 存在性检查，直接用 PopularProvider + 空历史。"""
    if algorithm != Algorithm.popular:
        raise APIError(422, "ALGORITHM_REQUIRES_AUTH",
            f"算法 {algorithm.value} 需要登录或历史用户身份以获取用户画像",
            {"algorithm": algorithm.value})
    from recommender.contracts import RecommendationRequest, RecommendationItem, RecommendationResult
    from datetime import datetime, timezone
    request = RecommendationRequest("app", 1, query.limit, "business", DATASET, SPLIT)
    provider = PROVIDERS[Algorithm.popular]
    # Popular.score 完全忽略 rated（只看 popularity.json），空历史即可
    scores = provider.score(request, {}, set())
    from recommender.student.common import select_top, utc_now, build_result
    ranked = select_top(scores, set(), query.limit)
    return build_result(Algorithm.popular, provider.model_version or "popular-v1", request, ranked)
