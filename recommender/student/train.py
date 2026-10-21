"""离线拟合脚本：按模式生成真实模型工件与侧车 manifest。

用法（在项目根目录）：
    python -m recommender.student.train --mode evaluation
    python -m recommender.student.train --mode business
只从该模式批准的评分文件拟合：evaluation 只用 evaluation/train.csv，business 只用
business/history_ratings.csv；特征只用 movies.csv / training-catalog.csv。
本模块不在导入时训练，必须显式调用 main()。
"""
from __future__ import annotations

import argparse
import json
import platform
from pathlib import Path

import numpy as np
import scipy
import scipy.sparse as sp

from ..data import DATASET, MANIFEST_SHA, PACKAGE, SCHEMA, SPLIT, FrozenData, sha256

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "models"
CATALOG_FEATURE = "training-catalog.csv"
GENRE_FEATURE = "movies.csv"

ALGORITHMS = ["popular", "content", "itemcf", "als", "cold_start"]
FEATURE_FILES = {
    "popular": [CATALOG_FEATURE],
    "content": [CATALOG_FEATURE, GENRE_FEATURE],
    "itemcf": [CATALOG_FEATURE],
    "als": [CATALOG_FEATURE],
    "cold_start": [CATALOG_FEATURE, GENRE_FEATURE],
}
ARTIFACTS = {
    "popular": ["popularity.json"],
    "content": ["item_features.json"],
    "itemcf": ["itemcf.npz", "popularity.json"],
    "als": ["als.npz", "popularity.json"],
    "cold_start": ["item_features.json", "popularity.json"],
}
PARAMETERS = {
    "popular": {"score": "train_rating_count"},
    "content": {"feature": "genres_onehot_l2", "profile": "rating_minus_2.5", "similarity": "cosine"},
    "itemcf": {"similarity": "cosine", "top_k_neighbors": 100, "weight": "rating", "min_similarity": 1e-6},
    "als": {"factors": 24, "iterations": 12, "alpha": 40.0, "reg": 0.05, "seed": 20261020, "feedback": "rating_confidence"},
    "cold_start": {"feature": "genres_onehot_l2", "profile": "rating_minus_2.5", "fallback": "popularity_when_no_support"},
}


def contract_manifest() -> dict:
    return json.loads((PACKAGE / "manifest.json").read_text(encoding="utf-8"))


def catalog_and_genres():
    data = FrozenData()
    catalog = data.catalog()
    genres_vocab = set()
    raw = {}
    for row in data.rows("movies.csv"):
        raw[row["movie_id"]] = [g for g in (row["genres"] or "").split("|") if g]
        genres_vocab.update(raw[row["movie_id"]])
    vocab = sorted(genres_vocab)
    index = {mid: k for k, mid in enumerate(sorted(catalog, key=int))}
    return catalog, raw, vocab, index


def genre_vectors(catalog, raw, vocab, index) -> dict[str, list[float]]:
    width = len(vocab)
    col = {g: j for j, g in enumerate(vocab)}
    vectors = {}
    for mid in catalog:
        vec = np.zeros(width, dtype="float64")
        for g in raw.get(mid, ()):
            vec[col[g]] = 1.0
        norm = float(np.linalg.norm(vec))
        if norm > 0.0:
            vec /= norm
        vectors[mid] = vec.tolist()
    return vectors


def read_ratings(mode: str) -> dict[str, dict[str, float]]:
    history: dict[str, dict[str, float]] = {}
    if mode == "evaluation":
        for row in FrozenData().training():
            history.setdefault(row["userId"], {})[row["movieId"]] = float(row["rating"])
        return history
    source = PACKAGE / "business/history_ratings.csv"
    expected = contract_manifest()["files"]["business/history_ratings.csv"]["sha256"]
    if not source.is_file() or sha256(source) != expected:
        raise SystemExit("business/history_ratings.csv 缺失或摘要不符，停止")
    import csv
    with source.open(encoding="utf-8", newline="") as stream:
        for row in csv.DictReader(stream):
            history.setdefault(row["userId"], {})[row["movieId"]] = float(row["rating"])
    return history


def popularity(catalog, history) -> dict[str, int]:
    counts = {mid: 0 for mid in catalog}
    for items in history.values():
        for mid in items:
            if mid in counts:
                counts[mid] += 1
    return counts


def fit_itemcf(history, catalog, index, neighbors: int = 100):
    item_count = len(catalog)
    users = sorted(history, key=int)
    uidx = {u: i for i, u in enumerate(users)}
    rows, cols, vals = [], [], []
    for u, items in history.items():
        j = uidx[u]
        for mid, rating in items.items():
            k = index.get(mid)
            if k is not None:
                rows.append(k); cols.append(j); vals.append(float(rating))
    X = sp.csr_matrix((vals, (rows, cols)), shape=(item_count, len(users)), dtype="float64")
    norms = np.sqrt(np.asarray(X.multiply(X).sum(axis=1)).ravel())
    norms[norms == 0] = 1.0
    inv = sp.diags(1.0 / norms)
    Xn = (inv @ X).tocsr()
    XnT = Xn.T.tocsr()
    out_rows, out_cols, out_vals = [], [], []
    block = 400
    for start in range(0, item_count, block):
        stop = min(start + block, item_count)
        dense = np.asarray((Xn[start:stop] @ XnT).todense())
        k = min(neighbors, dense.shape[1])
        cut = np.argpartition(-dense, k - 1, axis=1)[:, :k]
        for r in range(dense.shape[0]):
            cols_row = cut[r]
            sims = dense[r, cols_row]
            keep = sims > 1e-6
            if not keep.any():
                continue
            i = start + r
            out_rows.extend([i] * int(keep.sum()))
            out_cols.extend(int(c) for c in cols_row[keep])
            out_vals.extend(float(v) for v in sims[keep])
    S = sp.csr_matrix((out_vals, (out_rows, out_cols)), shape=(item_count, item_count), dtype="float64")
    return S


def fit_als(history, catalog, index, factors=24, iterations=12, alpha=40.0, reg=0.05, seed=20261020):
    rng = np.random.default_rng(seed)
    users = sorted(history, key=int)
    uidx = {u: i for i, u in enumerate(users)}
    item_ids = [mid for mid in sorted(catalog, key=int)]
    iidx = {mid: i for i, mid in enumerate(item_ids)}
    user_items: list[list[int]] = [[] for _ in users]
    user_conf: list[list[float]] = [[] for _ in users]
    item_users: list[list[int]] = [[] for _ in item_ids]
    item_conf: list[list[float]] = [[] for _ in item_ids]
    for u, items in history.items():
        ui = uidx[u]
        for mid, rating in items.items():
            j = iidx.get(mid)
            if j is None:
                continue
            conf = 1.0 + alpha * float(rating)
            user_items[ui].append(j); user_conf[ui].append(conf)
            item_users[j].append(ui); item_conf[j].append(conf)
    X = rng.normal(0.0, 0.01, (len(users), factors))
    Y = rng.normal(0.0, 0.01, (len(item_ids), factors))
    eye = np.eye(factors)
    for _ in range(iterations):
        YtY = Y.T @ Y + reg * eye
        for u in range(len(users)):
            js = user_items[u]
            if not js:
                continue
            Yu = Y[js]
            c = np.asarray(user_conf[u])[:, None]
            A = YtY + (Yu * (c - 1.0)).T @ Yu
            b = (c * Yu).sum(axis=0)
            X[u] = np.linalg.solve(A, b)
        XtX = X.T @ X + reg * eye
        for j in range(len(item_ids)):
            us = item_users[j]
            if not us:
                continue
            Xu = X[us]
            c = np.asarray(item_conf[j])[:, None]
            A = XtX + (Xu * (c - 1.0)).T @ Xu
            b = (c * Xu).sum(axis=0)
            Y[j] = np.linalg.solve(A, b)
    return np.asarray(users, dtype="int64"), np.asarray(item_ids, dtype="int64"), X, Y


def write_json(path: Path, payload) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, sort_keys=True), encoding="utf-8")


def build(mode: str, algorithms: list[str]) -> None:
    data = FrozenData()
    manifest = data.manifest
    catalog, raw, vocab, index = catalog_and_genres()
    history = read_ratings(mode)
    pop = popularity(catalog, history)
    features = genre_vectors(catalog, raw, vocab, index)
    tools = {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__}
    training = "evaluation/train.csv" if mode == "evaluation" else "business/history_ratings.csv"
    training_files = {training: manifest["files"][training]["sha256"]}

    for alg in algorithms:
        version = f"{alg}-v1"
        outdir = MODELS / mode / version
        outdir.mkdir(parents=True, exist_ok=True)
        if alg in ("popular", "itemcf", "als", "cold_start"):
            write_json(outdir / "popularity.json", pop)
        if alg in ("content", "cold_start"):
            write_json(outdir / "item_features.json", {"genres": vocab, "vectors": features})
        if alg == "itemcf":
            sp.save_npz(outdir / "itemcf.npz", fit_itemcf(history, catalog, index,
                                                          neighbors=PARAMETERS["itemcf"]["top_k_neighbors"]))
        if alg == "als":
            params = PARAMETERS["als"]
            uids, mids, X, Y = fit_als(history, catalog, index, factors=params["factors"],
                                       iterations=params["iterations"], alpha=params["alpha"],
                                       reg=params["reg"], seed=params["seed"])
            np.savez(outdir / "als.npz", user_ids=uids, item_ids=mids, user_factors=X, item_factors=Y)
        artifacts = {name: sha256(outdir / name) for name in ARTIFACTS[alg]}
        feature_files = {name: manifest["files"][name]["sha256"] for name in FEATURE_FILES[alg]}
        sidecar = {"algorithm": alg, "model_version": version, "runtime_mode": mode,
                   "dataset_version": DATASET, "split_version": SPLIT, "schema_version": SCHEMA,
                   "manifest_sha256": MANIFEST_SHA, "training_files": training_files,
                   "feature_files": feature_files, "artifacts": artifacts,
                   "parameters": PARAMETERS[alg], "tool_versions": tools}
        write_json(outdir / "manifest.json", sidecar)
        print(f"[{mode}] {alg}: {outdir} ({len(artifacts)} artifacts)")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["evaluation", "business"], required=True)
    parser.add_argument("--algorithms", nargs="*", default=ALGORITHMS, choices=ALGORITHMS)
    args = parser.parse_args(argv)
    build(args.mode, args.algorithms)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
