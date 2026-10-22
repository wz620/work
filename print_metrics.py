"""打印所有算法的 Precision@10 / Recall@10。"""
import json
from pathlib import Path

out = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1/evaluation-output")

print("=" * 70)
print(f"{'算法':15} {'分区':15} {'Precision@10':>13} {'Recall@10':>13} {'用户数':>8}")
print("=" * 70)
for f in sorted(out.glob("*.result.json")):
    d = json.loads(f.read_text(encoding="utf-8"))
    algo = d.get("algorithm", "?")
    part = d.get("partition", "?")
    p = d.get("precision_at_10", "?")
    r = d.get("recall_at_10", "?")
    u = d.get("user_count", "?")
    print(f"{algo:15} {part:15} {str(p):>13} {str(r):>13} {str(u):>8}")

# 三个课程核心算法的 validation 指标
print("\n" + "=" * 70)
print("课程统一验证分区 (validation)")
print("=" * 70)
for algo in ["popular", "content", "itemcf", "als", "cold_start"]:
    f = out / f"{algo}-validation.result.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        print(f"  {algo:15} P@10={d['precision_at_10']:.4f}  R@10={d['recall_at_10']:.4f}  ({d['user_count']} users)")
