"""给 ItemCF 算法加 explain() 函数：找出真实的协同相似度依据。"""
from __future__ import annotations

from pathlib import Path
import numpy as np


def load(manifest_path):
    import scipy.sparse as sp
    base = Path(manifest_path).resolve().parent
    return sp.load_npz(base / "itemcf.npz").tocsr()


def explain(manifest_path: str, movie_id: str, rated: dict[str, float], catalog_ids: tuple[str, ...]) -> dict:
    """
    返回 ItemCF 算法对 movie_id 的真实推荐依据：
    - 候选电影与用户评分过的每部电影之间的协同相似度
    - 哪些种子电影贡献了最终得分（权重 = similarity × rating）
    - 前 5 个最有贡献的协同配对
    """
    similarity = load(manifest_path)
    index = {mid: k for k, mid in enumerate(catalog_ids)}

    k_target = index.get(movie_id)
    if k_target is None:
        return {"found": False, "reason": "候选电影不在目录中"}

    # 重建得分：score = Σ sim(target, rated_movie) × rating
    # 与 itemcf.py 的 score() 完全一致：scores = similarity.T.dot(seed)
    contributions = []
    touched = False
    score_computed = 0.0
    for mid, rating in rated.items():
        k = index.get(mid)
        if k is not None:
            touched = True
            sim_ij = float(similarity[k_target, k])  # 候选电影 和 种子电影 的相似度
            contribution = sim_ij * float(rating)
            score_computed += contribution
            contributions.append({
                "seed_movie_id": mid,
                "rating": float(rating),
                "similarity": sim_ij,
                "contribution": contribution,
            })

    if not touched:
        return {"found": False, "reason": "用户没有评分历史"}

    # 按 |contribution| 降序排
    contributions.sort(key=lambda x: -abs(x["contribution"]))

    return {
        "found": True,
        "algorithm": "itemcf",
        "movie_id": movie_id,
        "score": score_computed,
        "top_contributions": contributions[:5],  # 前 5 个最有贡献的协同配对
        "total_seeds_used": len(contributions),
        "similarity_matrix_nnz": int(similarity.nnz),
    }
