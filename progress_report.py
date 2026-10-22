import json
from pathlib import Path

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")
POSTERS = ROOT / "frontend/public/posters"
JSON = ROOT / "frontend/public/movie-details.json"
TOTAL = 8459  # 数据库电影总数

jpg_ids = {f.stem for f in POSTERS.glob("*.jpg")}
json_data = json.loads(JSON.read_text(encoding="utf-8"))
json_ids_with_local = {k for k, v in json_data.items() if v.get("poster_local")}

need_json_sync = jpg_ids - json_ids_with_local
# 补齐 JSON（磁盘有但 JSON 没记录的）
for mid in need_json_sync:
    json_data.setdefault(mid, {})["poster_local"] = f"/posters/{mid}.jpg"
JSON.write_text(json.dumps(json_data, indent=2, ensure_ascii=False), encoding="utf-8")

with_local = sum(1 for v in json_data.values() if v.get("poster_local"))
with_tmdb = sum(1 for v in json_data.values() if v.get("tmdb_poster_path"))

pct = lambda x: f"{x/TOTAL*100:.1f}%"

print(f"==== 海报补全进度 ====")
print(f"数据库电影总数:     {TOTAL}")
print(f"本地 jpg 文件:       {len(jpg_ids)}  ({pct(len(jpg_ids))})")
print(f"movie-details.json:  {with_local} 有 poster_local / {len(json_data)} 条总记录")
print(f"其中有 tmdb_path:     {with_tmdb}")
print(f"补齐了 JSON 的新条目: {len(need_json_sync)}")
print(f"剩余缺海报:          {TOTAL - len(jpg_ids)} 部")
print(f"理论最终命中率:      约 50-70%（TMDB 可能搜不到一些电影）")
print(f"前端 fallback:        没海报的自动显示彩色渐变卡片")
