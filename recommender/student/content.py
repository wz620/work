"""内容(Content)算法：以真实 genres 特征构建用户画像，余弦相似召回。"""
from __future__ import annotations

from ..contracts import Algorithm, RecommendationRequest
from .common import BaseProvider, catalog_ids, load_json, manifest_dir


class ContentProvider(BaseProvider):
    algorithm = Algorithm.content

    def __init__(self, model_manifest_path, model_version: str = "", history_source: str | None = None):
        super().__init__(model_manifest_path, model_version, history_source)
        self._vectors = None
        self._matrix = None

    def _ensure(self):
        import numpy as np
        if self._vectors is None:
            payload = load_json(manifest_dir(self.model_manifest_path) / "item_features.json")
            self._vectors = payload["vectors"]
            ids = catalog_ids()
            width = len(payload["genres"])
            matrix = np.zeros((len(ids), width), dtype="float64")
            for k, mid in enumerate(ids):
                vec = self._vectors.get(mid)
                if vec is not None:
                    matrix[k] = vec
            self._matrix = matrix
        return self._vectors

    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        import numpy as np
        vectors = self._ensure()
        profile = np.zeros(self._matrix.shape[1], dtype="float64")
        for mid, rating in rated.items():
            vec = vectors.get(mid)
            if vec is not None:
                profile += (float(rating) - 2.5) * np.asarray(vec, dtype="float64")
        norm = float(np.linalg.norm(profile))
        if norm <= 0.0:
            return {}
        profile /= norm
        sims = self._matrix @ profile
        ids = catalog_ids()
        return {mid: float(sims[k]) for k, mid in enumerate(ids)}
