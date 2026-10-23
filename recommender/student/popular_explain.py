"""Popular（全局热门）的依据收集。

Popular 算法按 movies.popularity 字段降序排，依据就是"它是全站最热门的电影之一"。
"""
from __future__ import annotations

import json
from pathlib import Path


def explain(manifest: str, movie_id: str, rated: dict, catalog_ids: tuple[str, ...]) -> dict:
    """返回 Popular 算法里这部电影的全局排名和热度分。"""
    from pathlib import Path as _P
    manifest_path = _P(manifest)
    # manifest_path 可能是 manifest.json 文件路径，也可能是目录
    if manifest_path.is_file():
        base = manifest_path.parent
    else:
        base = manifest_path

    model_version = "popular-v1"
    try:
        with open(base / "manifest.json", encoding="utf-8") as f:
            model_version = json.load(f).get("version", model_version)
    except OSError:
        pass

    # 课程 Popular 模型用 popularity.json（{movie_id: score} dict）
    try:
        with open(base / "popularity.json", encoding="utf-8") as f:
            popularity = json.load(f)
    except OSError:
        popularity = {}

    if not isinstance(popularity, dict) or movie_id not in popularity:
        return {"found": False, "algorithm": "popular", "movie_id": movie_id,
                "reason": "不在热门榜单中"}

    # 按 score 降序排，算 global_rank
    sorted_scores = sorted(popularity.values(), reverse=True)
    score = float(popularity[movie_id])
    rank = next((i + 1 for i, s in enumerate(sorted_scores) if s == score), None)

    return {
        "found": True, "algorithm": "popular", "movie_id": movie_id,
        "score": score,
        "global_rank": rank,
        "total_popular": len(popularity),
        "model_version": model_version,
    }
