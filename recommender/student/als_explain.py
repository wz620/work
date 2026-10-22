"""ALS 推荐算法的依据收集。

ALS（Alternating Least Squares）是矩阵分解算法：把 user-item 评分矩阵分解成 user_factors
和 item_factors（均为 latent 向量），最终得分 = dot(user_vector, item_vector)。

**真实依据**：把 item_factors 的每个 latent 维度贡献（user_vec[d] × item_vec[d]）
拆开，按 |contribution| 排序，找出最影响最终得分的几个维度。
"""
from __future__ import annotations

import json
import math
from pathlib import Path


def explain(manifest: str, movie_id: str, rated: dict, catalog_ids: tuple[str, ...]) -> dict:
    """给 ALS 模型里的某部电影生成真实依据。

    Returns:
        {"found": bool, "algorithm": "als", "movie_id": str, "score": float,
         "top_latent_dims": [{"dim": int, "user_component": float, "item_component": float,
                              "contribution": float}],
         "model_version": str}
    """
    manifest_path = Path(manifest)
    user_vec, item_vec, user_index, item_index, model_version = _load(manifest_path)
    if user_vec is None or item_vec is None:
        return {"found": False, "algorithm": "als", "movie_id": movie_id, "reason": "ALS 模型文件缺失"}
    # 把 movie_id 字符串 → item latent 向量行号
    item_idx = item_index.get(movie_id)
    if item_idx is None:
        # 找不到 → 尝试按 movie_id 数值匹配 catalog_ids
        try:
            mid_int = int(movie_id)
            for pos, cid in enumerate(catalog_ids):
                if int(cid) == mid_int:
                    item_idx = pos
                    break
        except (ValueError, TypeError):
            pass
    if item_idx is None:
        return {"found": False, "algorithm": "als", "movie_id": movie_id,
                "reason": f"电影 {movie_id} 不在 ALS item_factors 里"}
    # 用 user 平均 latent 向量作为"用户画像"近似（课程 ALS 没 per-user factor 导出）
    user_profile = user_vec.mean(axis=0).A1
    item_factors = item_vec[item_idx].A1
    score = float(user_profile.dot(item_factors))
    # 拆分每个 latent 维度的贡献
    dims = []
    for d, (uv, iv) in enumerate(zip(user_profile, item_factors)):
        dims.append({
            "dim": d,
            "user_component": float(round(uv, 4)),
            "item_component": float(round(iv, 4)),
            "contribution": float(round(uv * iv, 4)),
        })
    dims.sort(key=lambda x: abs(x["contribution"]), reverse=True)
    return {
        "found": True, "algorithm": "als", "movie_id": movie_id,
        "score": score,
        "top_latent_dims": dims[:8],
        "model_version": model_version,
    }


def _load(manifest_path: Path):
    """从 ALS manifest 路径里找 item_factors.npz / user_factors.npz 并加载。"""
    import numpy as np
    try:
        with open(manifest_path / "manifest.json", encoding="utf-8") as f:
            manifest_data = json.load(f)
    except OSError:
        manifest_data = {}
    model_version = manifest_data.get("version") or "als-v1"
    base = manifest_path
    user_vec, item_vec = None, None
    user_index, item_index = {}, {}
    for name in manifest_data.get("files", {}).keys() if isinstance(manifest_data.get("files"), dict) else []:
        pass
    for fname in base.glob("*.npz"):
        try:
            d = np.load(fname, allow_pickle=True)
            keys = list(d.keys())
            if "item_factors" in keys:
                item_vec = d["item_factors"]
                if "item_ids" in keys:
                    item_index = {str(v): i for i, v in enumerate(d["item_ids"])}
            if "user_factors" in keys:
                user_vec = d["user_factors"]
        except Exception:
            continue
    # 如果没拆开来，可能是单文件
    if user_vec is None and item_vec is None:
        for fname in base.glob("*.npz"):
            try:
                d = np.load(fname, allow_pickle=True)
                keys = list(d.keys())
                if len(keys) >= 2:
                    # 启发式：先 item 后 user
                    for i, k in enumerate(keys):
                        arr = d[k]
                        if arr.ndim == 2:
                            if item_vec is None:
                                item_vec = arr
                            elif user_vec is None:
                                user_vec = arr
                if item_vec is not None and "item_ids" in keys:
                    item_index = {str(v): i for i, v in enumerate(d["item_ids"])}
            except Exception:
                continue
    return user_vec, item_vec, user_index, item_index, model_version
