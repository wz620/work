"""ItemCF 算法：物品-物品余弦相似度（训练共现），按用户历史加权累加召回。"""
from __future__ import annotations

from ..contracts import Algorithm, RecommendationRequest
from .common import BaseProvider, catalog_ids, manifest_dir


class ItemCFProvider(BaseProvider):
    algorithm = Algorithm.itemcf

    def __init__(self, model_manifest_path, model_version: str = "", history_source: str | None = None):
        super().__init__(model_manifest_path, model_version, history_source)
        self._similarity = None

    def _ensure(self):
        if self._similarity is None:
            import scipy.sparse as sp
            self._similarity = sp.load_npz(manifest_dir(self.model_manifest_path) / "itemcf.npz").tocsr()
        return self._similarity

    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        import numpy as np
        similarity = self._ensure()
        ids = catalog_ids()
        index = {mid: k for k, mid in enumerate(ids)}
        seed = np.zeros(len(ids), dtype="float64")
        touched = False
        for mid, rating in rated.items():
            k = index.get(mid)
            if k is not None:
                seed[k] = float(rating)
                touched = True
        if not touched:
            return {}
        scores = similarity.T.dot(seed)
        return {mid: float(scores[k]) for k, mid in enumerate(ids)}
