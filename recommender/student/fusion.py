"""S1：多路召回的 RRF（Reciprocal Rank Fusion）融合服务。

只读、不写数据库：逐路调用 `recommender.contracts.recommend()` 复用已注册的
Provider（popular/content/itemcf/als/cold_start），按 RRF 公式融合名次，
产出带 `recall_sources` / `recall_ranks` / `fusion_rank` 的融合清单。

不修改 `Algorithm` 枚举：RRF 不是第六种算法，而是对既有算法输出的融合层。
"""
from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field

from ..contracts import Algorithm, RecommendationRequest, recommend
from ..data import DATASET, SPLIT

RRF_K = 60
DEFAULT_SOURCES = ("popular", "content", "itemcf", "als", "cold_start")
# 单路召回条数：受契约 limit 上限约束，融合只需名次，50 条足够。
PER_SOURCE = 50


@dataclass(frozen=True)
class FusedItem:
    movie_id: str
    score: float
    fusion_rank: int
    recall_sources: list[str]
    recall_ranks: dict[str, int]


@dataclass
class FusedResult:
    subject_key: str
    runtime_mode: str
    k: int
    sources: list[str]
    weights: dict[str, float]
    items: list[FusedItem] = field(default_factory=list)

    def as_payload(self) -> dict:
        return {
            "status": "ready",
            "subject_key": self.subject_key,
            "runtime_mode": self.runtime_mode,
            "k": self.k,
            "sources": self.sources,
            "weights": self.weights,
            "items": [
                {"movie_id": item.movie_id, "fusion_rank": item.fusion_rank, "score": round(item.score, 10),
                 "recall_sources": item.recall_sources, "recall_ranks": item.recall_ranks}
                for item in self.items
            ],
        }


def rrf_fuse(rankings: dict[str, list[str]], k: int = RRF_K,
             weights: dict[str, float] | None = None) -> list[FusedItem]:
    """RRF 融合：score(m) = Σ_s w_s / (k + rank_s(m))；同分按 movie_id 数值升序。"""
    if k < 0:
        raise ValueError("k 不能为负数")
    weights = weights or {}
    totals: dict[str, float] = {}
    ranks: dict[str, dict[str, int]] = {}
    for source, ordered in rankings.items():
        weight = float(weights.get(source, 1.0))
        if weight == 0.0:
            continue
        for position, movie_id in enumerate(ordered, 1):
            if source in ranks.get(movie_id, {}):
                continue
            totals[movie_id] = totals.get(movie_id, 0.0) + weight / (k + position)
            ranks.setdefault(movie_id, {})[source] = position
    ordered_rows = [(mid, totals[mid], ranks[mid]) for mid in totals]
    ordered_rows.sort(key=lambda row: (-row[1], int(row[0])))
    return [FusedItem(mid, score, rank, sorted(source_ranks), source_ranks)
            for rank, (mid, score, source_ranks) in enumerate(ordered_rows, 1)]


def multi_recall(request: RecommendationRequest, sources=DEFAULT_SOURCES,
                 per_source: int = PER_SOURCE) -> dict[str, list[str]]:
    """逐路调用既有 Provider，返回 {来源: 有序 movie_id 列表}。非法或未注册来源原样抛错。"""
    rankings: dict[str, list[str]] = {}
    for name in sources:
        algorithm = Algorithm(name)
        leg = recommend(algorithm, RecommendationRequest(
            request.subject_kind, request.subject_id, per_source,
            request.runtime_mode, request.dataset_version, request.split_version))
        rankings[name] = [item.movie_id for item in leg.items]
    return rankings


def fuse(request: RecommendationRequest, sources=DEFAULT_SOURCES, limit: int = 10,
         k: int = RRF_K, weights: dict[str, float] | None = None) -> FusedResult:
    """完整融合：多路召回 → RRF → 截断到 limit。"""
    source_list = list(sources)
    weight_map = {name: float((weights or {}).get(name, 1.0)) for name in source_list}
    rankings = multi_recall(request, source_list)
    fused = rrf_fuse(rankings, k, weight_map)[:limit]
    subject_key = f"{request.subject_kind}:{request.subject_id}"
    return FusedResult(subject_key, request.runtime_mode, k, source_list, weight_map, fused)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="S1 RRF 融合（只读）")
    parser.add_argument("--subject-kind", choices=["ml", "app"], default="ml")
    parser.add_argument("--subject-id", type=int, required=True)
    parser.add_argument("--sources", nargs="*", default=list(DEFAULT_SOURCES))
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--k", type=int, default=RRF_K)
    parser.add_argument("--runtime-mode", choices=["business", "evaluation"], default="business")
    args = parser.parse_args(argv)
    if args.runtime_mode == "evaluation":
        # 评价模式使用评价清单 Provider（与 recommender.student.eval_entry 一致）。
        from . import eval_entry  # noqa: F401
    request = RecommendationRequest(args.subject_kind, args.subject_id, PER_SOURCE,
                                     args.runtime_mode, DATASET, SPLIT)
    result = fuse(request, args.sources, args.limit, args.k)
    print(json.dumps(result.as_payload(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
