"""Popular（全局热门）的依据收集。

Popular 算法按 movies.popularity 字段降序排，依据就是"它是全站最热门的电影之一"。
"""
from __future__ import annotations

import json
from pathlib import Path


def explain(manifest: str, movie_id: str, rated: dict, catalog_ids: tuple[str, ...]) -> dict:
    """返回 Popular 算法里这部电影的全局排名和热度分。"""
    manifest_path = Path(manifest)
    model_version = "popular-v1"
    try:
        with open(manifest_path / "manifest.json", encoding="utf-8") as f:
            model_version = json.load(f).get("version", model_version)
    except OSError:
        pass

    # 从 Catalog manifest 拿完整热门排序
    try:
        rankings_path = manifest_path / "popular_rankings.json"
        with open(rankings_path, encoding="utf-8") as f:
            ranking = json.load(f)
    except OSError:
        ranking = []

    # ranking 应该是 [{movie_id: str, popularity: float}, ...] 按热度降序
    found_entry = None
    for pos, entry in enumerate(ranking):
        mid = str(entry.get("movie_id", entry.get("mid", "")))
        if mid == movie_id:
            found_entry = entry
            return {
                "found": True, "algorithm": "popular", "movie_id": movie_id,
                "score": float(entry.get("popularity", entry.get("score", 0))),
                "global_rank": pos + 1,
                "total_popular": len(ranking),
                "model_version": model_version,
            }
    return {"found": False, "algorithm": "popular", "movie_id": movie_id,
            "reason": "不在热门 Top-N 榜单中"}
