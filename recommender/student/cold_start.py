"""冷启动(ColdStart)算法：用极少量 support 历史构建内容画像，无支持时回退热门。"""
from __future__ import annotations

from ..contracts import Algorithm, RecommendationRequest
from .common import BaseProvider, catalog_ids, load_json, manifest_dir


class ColdStartProvider(BaseProvider):
    algorithm = Algorithm.cold_start

    def __init__(self, model_manifest_path, model_version: str = "", history_source: str | None = None):
        super().__init__(model_manifest_path, model_version, history_source)
        self._vectors = None
        self._popularity = None

    def _ensure(self):
        if self._vectors is None:
            base = manifest_dir(self.model_manifest_path)
            self._vectors = load_json(base / "item_features.json")["vectors"]
            self._popularity = load_json(base / "popularity.json")
        return self._vectors, self._popularity

    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        import numpy as np
        vectors, popularity = self._ensure()
        ids = catalog_ids()
        width = len(next(iter(vectors.values()))) if vectors else 0
        profile = np.zeros(width, dtype="float64")
        used = 0
        for mid, rating in rated.items():
            vec = vectors.get(mid)
            if vec is not None:
                profile += (float(rating) - 2.5) * np.asarray(vec, dtype="float64")
                used += 1
        norm = float(np.linalg.norm(profile))
        if used == 0 or norm <= 0.0:
            # k=0（无任何交互）不声称个性化：明确回退到热门清单。
            return {mid: float(count) for mid, count in popularity.items()}
        profile /= norm
        scores = {}
        for mid in ids:
            vec = vectors.get(mid)
            if vec is not None:
                scores[mid] = float(np.dot(np.asarray(vec, dtype="float64"), profile))
        return scores
