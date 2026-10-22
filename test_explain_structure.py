"""快速测试 itemcf.npz 和 content item_features.json 结构。"""
import json, numpy as np, scipy.sparse as sp
from pathlib import Path

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")

# 1) Content: 看一个电影的 genres 向量和 catalog
content_dir = ROOT / "models/business/content-v1"
content_feat = json.loads((content_dir / "item_features.json").read_text(encoding="utf-8"))
genres = content_feat["genres"]
vectors = content_feat["vectors"]
print(f"Content: {len(genres)} genres = {genres}")
print(f"Content: {len(vectors)} movies have vectors")
# 示例：toy story (1)
mid = "1"
print(f"\nmovie_id=1 vector: {vectors.get(mid)}")
print(f"movie_id=1 genres indices: {[genres[i] for i,v in enumerate(vectors.get(mid)) if v == 1]}")

# 2) ItemCF: 相似度矩阵形状
itemcf_dir = ROOT / "models/business/itemcf-v1"
sim = sp.load_npz(itemcf_dir / "itemcf.npz").tocsr()
print(f"\nItemCF similarity matrix: shape={sim.shape} nnz={sim.nnz}")

# 3) catalog_ids 就是 8459 个 movie_id 按数值升序
from recommender.student.common import catalog_ids
ids = catalog_ids()
print(f"\ncatalog_ids: len={len(ids)}, first 5={ids[:5]}, last 5={ids[-5:]}")
# index 映射
index = {mid: k for k, mid in enumerate(ids)}
# movie_id=1 在 index=0
print(f"\nmovie_id='1' → index={index.get('1')}")

# 4) 示例：找 movie_id=1 和 movie_id=318 的相似度
k1 = index.get("1"); k318 = index.get("318")
if k1 is not None and k318 is not None:
    print(f"sim[1,318] = {sim[k1, k318]:.4f}")
    print(f"sim[318,1] = {sim[k318, k1]:.4f}")

# 5) movie_id=318 最相似的 5 部
k = index.get("318")
row = sim.getrow(k).toarray().flatten()
top_k = 6  # 包含自身
top_idx = row.argsort()[::-1][:top_k]
print(f"\nmovie_id=318 最相似的 {top_k} 部:")
for idx in top_idx:
    print(f"  {ids[idx]} (sim={row[idx]:.4f})")
