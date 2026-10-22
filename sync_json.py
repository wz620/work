"""把磁盘有 jpg 但 JSON 里没 poster_local 的条目补上（合并当前脚本进度）。"""
import json
from pathlib import Path

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")
POSTERS = ROOT / "frontend/public/posters"
DETAILS = ROOT / "frontend/public/movie-details.json"

d = json.loads(DETAILS.read_text(encoding="utf-8"))

jpg_ids = {f.stem for f in POSTERS.glob("*.jpg")}
json_ids = {k for k, v in d.items() if v.get("poster_local")}
need_add = jpg_ids - json_ids

print(f"JSON 已有 poster_local: {len(json_ids)}")
print(f"磁盘 jpg 总数: {len(jpg_ids)}")
print(f"需补到 JSON: {len(need_add)} 部")

for mid in need_add:
    d.setdefault(mid, {})["poster_local"] = f"/posters/{mid}.jpg"

DETAILS.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

has = sum(1 for v in d.values() if v.get("poster_local"))
print(f"\n合并后: JSON {len(d)} 条, 有 poster_local {has} 条")
