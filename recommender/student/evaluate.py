"""离线评价执行器：逐用户真实预测 → predictions.jsonl，并计算 Precision@10/Recall@10。

用法（项目根目录）：
    python -m recommender.student.evaluate --algorithm itemcf --partition validation
    python -m recommender.student.evaluate --algorithm cold_start --partition cold-k5
不训练、不改数据库；只读该分区允许的冻结文件。候选人 = 目录 − 对应已评分；正例 = 留出/query 中 ≥4.0。
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from ..contracts import RecommendationRequest
from ..data import DATASET, SPLIT, SCHEMA, FrozenData, sha256
from ..evaluation import eligible_users, task
from .als import ALSProvider
from .cold_start import ColdStartProvider
from .common import frozen_history
from .content import ContentProvider
from .itemcf import ItemCFProvider
from .popular import PopularProvider

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
PROVIDERS = {
    "popular": PopularProvider, "content": ContentProvider, "itemcf": ItemCFProvider,
    "als": ALSProvider, "cold_start": ColdStartProvider,
}
# 分区 → (历史来源, 标签文件, 额外排除来源)
PARTITIONS = {
    "validation": ("evaluation/train.csv", "evaluation/validation.csv", ["evaluation/train.csv"]),
    "test": ("evaluation/train.csv", "evaluation/test.csv",
             ["evaluation/train.csv", "evaluation/validation.csv"]),
    "cold-k0": ("evaluation/cold-k0-support.csv", "evaluation/cold-k0-query.csv", ["evaluation/cold-k0-support.csv"]),
    "cold-k1": ("evaluation/cold-k1-support.csv", "evaluation/cold-k1-query.csv", ["evaluation/cold-k1-support.csv"]),
    "cold-k5": ("evaluation/cold-k5-support.csv", "evaluation/cold-k5-query.csv", ["evaluation/cold-k5-support.csv"]),
    "cold-k10": ("evaluation/cold-k10-support.csv", "evaluation/cold-k10-query.csv", ["evaluation/cold-k10-support.csv"]),
}


def load_labels(name: str) -> dict[str, set[str]]:
    labels: dict[str, set[str]] = defaultdict(set)
    for uid, items in frozen_history(name).items():
        for mid, rating in items.items():
            if rating >= 4.0:
                labels[uid].add(mid)
    return labels


def exclusions(name: str, users: set[str]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {uid: set() for uid in users}
    for uid, items in frozen_history(name).items():
        if uid in result:
            result[uid] = set(items)
    return result


def run(algorithm: str, partition: str, out_dir: Path, limit: int = 10) -> dict:
    history_source, label_file, exclude_files = PARTITIONS[partition]
    model_path = MODELS / "evaluation" / f"{algorithm}-v1" / "manifest.json"
    manifest = json.loads(model_path.read_text(encoding="utf-8"))
    model_version = manifest["model_version"]
    provider = PROVIDERS[algorithm](model_path, model_version, history_source=history_source)
    users = eligible_users(FrozenData(), partition)
    blocked: dict[str, set[str]] = {uid: set() for uid in users}
    for name in exclude_files:
        for uid, items in frozen_history(name).items():
            if uid in blocked:
                blocked[uid] |= set(items)
    labels = load_labels(label_file)
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_path = out_dir / f"{algorithm}-{partition}.jsonl"
    hits = 0
    recall_sum = 0.0
    ordered = sorted(users, key=int)
    with pred_path.open("w", encoding="utf-8") as stream:
        for uid in ordered:
            request = RecommendationRequest("ml", int(uid), limit, "evaluation", DATASET, SPLIT)
            result = provider.recommend(request, exclude=blocked[uid])
            stream.write(json.dumps({"ml_user_id": uid, "result": result.model_dump(mode="json")},
                                    ensure_ascii=False) + "\n")
            recommended = {item.movie_id for item in result.items}
            positives = labels.get(uid, set())
            overlap = recommended & positives
            hits += len(overlap)
            if positives:
                recall_sum += len(overlap) / len(positives)
    user_count = len(users)
    precision = hits / (limit * user_count) if user_count else 0.0
    recall = recall_sum / user_count if user_count else 0.0
    current = task(FrozenData(), partition)
    evaluation = {"status": "completed", "runtime_mode": "evaluation", "algorithm": algorithm,
                  "model_version": model_version, "task_sha256": current["task_sha256"],
                  "model_manifest_sha256": sha256(model_path), "dataset_version": DATASET,
                  "split_version": SPLIT, "schema_version": SCHEMA, "partition": partition,
                  "user_count": user_count, "precision_at_10": round(precision, 6), "recall_at_10": round(recall, 6)}
    result_path = out_dir / f"{algorithm}-{partition}.result.json"
    result_path.write_text(json.dumps(evaluation, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"algorithm": algorithm, "partition": partition, "users": user_count,
            "precision_at_10": evaluation["precision_at_10"], "recall_at_10": evaluation["recall_at_10"],
            "predictions": str(pred_path), "evaluation_result": str(result_path)}


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--algorithm", choices=list(PROVIDERS), required=True)
    parser.add_argument("--partition", choices=list(PARTITIONS), required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "evaluation-output")
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args(argv)
    print(json.dumps(run(args.algorithm, args.partition, args.out_dir, args.limit),
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
