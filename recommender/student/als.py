"""ALS 算法：隐式反馈矩阵分解（交替最小二乘），用训练因子对全部物品打分。"""
from __future__ import annotations

from ..contracts import Algorithm, RecommendationRequest
from .common import BaseProvider, load_json, manifest_dir


class ALSProvider(BaseProvider):
    algorithm = Algorithm.als

    def __init__(self, model_manifest_path, model_version: str = "", history_source: str | None = None):
        super().__init__(model_manifest_path, model_version, history_source)
        self._loaded = None

    def _ensure(self):
        if self._loaded is None:
            import numpy as np
            base = manifest_dir(self.model_manifest_path)
            payload = np.load(base / "als.npz")
            user_ids = [str(u) for u in payload["user_ids"]]
            self._loaded = {
                "index": {uid: k for k, uid in enumerate(user_ids)},
                "item_ids": [str(m) for m in payload["item_ids"]],
                "user_factors": payload["user_factors"].astype("float64"),
                "item_factors": payload["item_factors"].astype("float64"),
                "popularity": load_json(base / "popularity.json"),
            }
        return self._loaded

    def score(self, request: RecommendationRequest, rated: dict[str, float], block: set[str]) -> dict[str, float]:
        model = self._ensure()
        row = model["index"].get(str(request.subject_id))
        if row is None:
            # 训练中不存在的用户（如业务新账号）回退到热门，不伪造个性化分数。
            return {mid: float(count) for mid, count in model["popularity"].items()}
        scores = model["item_factors"] @ model["user_factors"][row]
        return {model["item_ids"][k]: float(scores[k]) for k in range(len(model["item_ids"]))}
