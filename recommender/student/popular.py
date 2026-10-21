"""热门(Popular)算法：按训练集评分次数降序召回，属于非个性化基线。"""
from __future__ import annotations

from ..contracts import Algorithm, RecommendationRequest
from .common import BaseProvider, load_json, manifest_dir


class PopularProvider(BaseProvider):
    algorithm = Algorithm.popular

    def __init__(self, model_manifest_path, model_version: str = "", history_source: str | None = None):
        super().__init__(model_manifest_path, model_version, history_source)
        self._popularity = None

    def _ensure(self) -> dict[str, int]:
        if self._popularity is None:
            self._popularity = load_json(manifest_dir(self.model_manifest_path) / "popularity.json")
        return self._popularity

    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        return {mid: float(count) for mid, count in self._ensure().items()}
