"""学生算法的公共工具：冻结目录、历史读取、工件加载、Top-N 排序与 DTO 构建。

只读冻结数据；不在导入时训练或写数据库。numpy/scipy 延迟导入，避免无依赖环境导入失败。
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

from ..contracts import Algorithm, RecommendationItem, RecommendationRequest, RecommendationResult
from ..data import FrozenData, require

# 评价分区各自允许的历史来源（不含标签/query，避免偷读）。
VALIDATION_HISTORY = "evaluation/train.csv"
TEST_HISTORY = "evaluation/train.csv"
COLD_SUPPORT = {f"cold-k{k}": f"evaluation/cold-k{k}-support.csv" for k in (0, 1, 5, 10)}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_json(path: Path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def manifest_dir(manifest_path) -> Path:
    return Path(manifest_path).resolve().parent


@lru_cache(maxsize=None)
def catalog_ids() -> tuple[str, ...]:
    """批准目录（8,459 部），按 movie_id 数值升序。"""
    data = FrozenData()
    ids = tuple(sorted(data.catalog(), key=int))
    require(len(ids) == 8459, "目录数量不符", "DATA_IDENTITY_INVALID")
    return ids


@lru_cache(maxsize=None)
def frozen_history(name: str) -> dict[str, dict[str, float]]:
    """读取冻结评价历史文件为 {userId: {movieId: rating}}（仅评价白名单文件）。"""
    data = FrozenData()
    history: dict[str, dict[str, float]] = defaultdict(dict)
    for row in data.rows(name, evaluation=True):
        history[row["userId"]][row["movieId"]] = float(row["rating"])
    return {uid: dict(items) for uid, items in history.items()}


@lru_cache(maxsize=None)
def train_history() -> dict[str, dict[str, float]]:
    """训练集历史 {userId: {movieId: rating}}（唯一允许的拟合输入）。"""
    data = FrozenData()
    history: dict[str, dict[str, float]] = defaultdict(dict)
    for row in data.training():
        history[row["userId"]][row["movieId"]] = float(row["rating"])
    return {uid: dict(items) for uid, items in history.items()}


def select_top(scores: dict[str, float], exclude: set[str], limit: int) -> list[tuple[str, float]]:
    """过滤排除集合，按 分数降序、movie_id 数值升序 取前 limit 个。"""
    ranked = [(mid, float(score)) for mid, score in scores.items() if mid not in exclude]
    ranked.sort(key=lambda pair: (-pair[1], int(pair[0])))
    return ranked[:limit]


def build_result(algorithm: Algorithm, model_version: str, request: RecommendationRequest,
                 ranked: list[tuple[str, float]]) -> RecommendationResult:
    items = [RecommendationItem(movie_id=mid, rank=rank, algorithm=algorithm,
                                model_version=model_version, score=float(score))
             for rank, (mid, score) in enumerate(ranked, 1)]
    return RecommendationResult(algorithm=algorithm, model_version=model_version,
        dataset_version=request.dataset_version, split_version=request.split_version,
        runtime_mode=request.runtime_mode, generated_at=utc_now(), items=items)


class BaseProvider:
    """五个算法共用的输入装配：业务读数据库历史，评价读冻结文件历史。"""

    algorithm: Algorithm
    # 评价模式使用的冻结历史文件；业务模式为 None（改走 business.read_history）。
    history_source: str | None = "evaluation/train.csv"

    def __init__(self, model_manifest_path, model_version: str, history_source: str | None = None):
        self.model_manifest_path = Path(model_manifest_path)
        self.model_version = model_version
        if history_source is not None:
            self.history_source = history_source

    # ---- 历史读取 -------------------------------------------------------------
    def rated(self, request: RecommendationRequest) -> dict[str, float]:
        if request.runtime_mode == "business":
            try:
                from ..business import read_history
                history = read_history(request)
            except Exception as exc:  # 业务历史适配错误原样抛出，不伪造结果
                raise
            self._last_favorites = history.favorite_movie_ids
            return {fb.movie_id: float(fb.rating) for fb in history.ratings}
        if self.history_source is None:
            self._last_favorites = ()
            return {}
        self._last_favorites = ()
        return dict(frozen_history(self.history_source).get(str(request.subject_id), {}))

    def recommend(self, request: RecommendationRequest, *, exclude: set[str] | None = None):
        rated = self.rated(request)
        block = set(rated)
        # 把已收藏但未评分的电影也加入 block——用户已表达过偏好，不应再推荐
        favorites = getattr(self, "_last_favorites", ())
        if favorites:
            block |= {str(mid) for mid in favorites}
        if exclude:
            block |= {str(mid) for mid in exclude}
        scores = self.score(request, rated, block)
        ranked = select_top(scores, block, request.limit)
        return build_result(self.algorithm, self.model_version, request, ranked)

    # ---- 子类实现 -------------------------------------------------------------
    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        raise NotImplementedError
