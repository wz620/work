"""给 Content 算法加 explain() 函数：找出真实的 genres 匹配依据。"""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np


def load(manifest_path):
    """加载 item_features.json（genres + vectors）。"""
    base = Path(manifest_path).resolve().parent
    payload = json.loads((base / "item_features.json").read_text(encoding="utf-8"))
    return payload["genres"], payload["vectors"]


def explain(manifest_path: str, movie_id: str, rated: dict[str, float], catalog_ids) -> dict:
    """
    返回 Content 算法对 movie_id 的真实推荐依据：
    - 候选电影的 genres
    - 用户历史高评分电影（rating > 3.0）以及它们的 genres
    - 最终影响打分的 genres 特征（profile 中非零分量 + 候选电影有对应 genre）
    """
    genres, vectors = load(manifest_path)
    if movie_id not in vectors:
        return {"found": False, "reason": "候选电影没有内容向量"}

    target_vec = np.asarray(vectors[movie_id], dtype="float64")
    target_genres = [genres[i] for i, v in enumerate(target_vec) if v > 0.01]

    # 重建用户画像（与 content.py 的 score() 完全一致的公式）
    profile = np.zeros(len(genres), dtype="float64")
    user_genre_evidence = []  # [{"movie_id":.., "rating":.., "genres": [...]}]
    for mid, rating in rated.items():
        vec = vectors.get(mid)
        if vec is not None:
            vec_arr = np.asarray(vec, dtype="float64")
            profile += (float(rating) - 2.5) * vec_arr
            if rating > 3.0:
                user_genre_evidence.append({
                    "movie_id": mid,
                    "rating": float(rating),
                    "genres": [genres[i] for i, v in enumerate(vec_arr) if v > 0.01],
                })

    # 找到真正影响打分的 genres：候选电影有 且 profile 有非零分量
    contributing_genres = []
    for i, g in enumerate(genres):
        if target_vec[i] > 0.01 and abs(profile[i]) > 0.01:
            contributing_genres.append({
                "genre": g,
                "profile_weight": float(profile[i]),  # 正=偏好, 负=厌恶
                "target_has": True,
            })
    # 按 |weight| 降序
    contributing_genres.sort(key=lambda x: -abs(x["profile_weight"]))

    # 最终得分（与 score() 一致）
    norm = float(np.linalg.norm(profile))
    score = 0.0
    if norm > 0:
        score = float(np.dot(target_vec, profile / norm))

    return {
        "found": True,
        "algorithm": "content",
        "movie_id": movie_id,
        "score": score,
        "target_genres": target_genres,
        "contributing_genres": contributing_genres[:6],  # 取前 6 个最重要的
        "user_high_rated_count": len(user_genre_evidence),
        "user_history_genres_sample": user_genre_evidence[:5],
    }
