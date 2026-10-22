"""把 evaluation-output 下的 *.result.json 复制到 frontend/public/evaluation/ 供前端读取。"""
import json, shutil
from pathlib import Path

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")
SRC = ROOT / "evaluation-output"
DST = ROOT / "frontend/public/evaluation"

DST.mkdir(parents=True, exist_ok=True)

# 1. 逐个复制 result.json，重命名为 {algorithm}-{partition}.json 便于前端 fetch
for f in SRC.glob("*.result.json"):
    target = DST / f.name.replace(".result.json", ".json")
    shutil.copy2(f, target)
    print(f"  ✓ {f.name} → {target.name}")

# 2. 额外生成一个 validation 分区的汇总 manifest（5 个核心算法的 P@10/R@10 对比表）
summary = {"partition": "validation", "algorithms": {}}
for algo in ["popular", "content", "itemcf", "als", "cold_start"]:
    f = SRC / f"{algo}-validation.result.json"
    if f.exists():
        d = json.loads(f.read_text(encoding="utf-8"))
        summary["algorithms"][algo] = {
            "precision_at_10": d["precision_at_10"],
            "recall_at_10": d["recall_at_10"],
            "model_version": d["model_version"],
            "user_count": d["user_count"],
        }

summary_path = DST / "validation-summary.json"
summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\n  ✓ validation-summary.json — 5 算法对比表")

# 3. 打印对比
print("\n" + "=" * 60)
print(f"{'算法':15} {'P@10':>8} {'R@10':>8} {'模型':12}")
print("-" * 60)
for algo, m in summary["algorithms"].items():
    print(f"{algo:15} {m['precision_at_10']:>8.4f} {m['recall_at_10']:>8.4f} {m['model_version']:12}")
print("=" * 60)
print(f"\n共 {len(list(DST.glob('*.json')))} 个文件 → /evaluation/*.json")
