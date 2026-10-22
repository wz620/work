import json
from pathlib import Path
p = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1/frontend/public/movie-details.json")
d = json.loads(p.read_text(encoding="utf-8"))
has_local = {k: v for k, v in d.items() if v.get("poster_local")}
has_tmdb = {k: v for k, v in d.items() if v.get("tmdb_poster_path")}
print(f"JSON 总条目: {len(d)}")
print(f"有 poster_local: {len(has_local)}")
print(f"有 tmdb_poster_path: {len(has_tmdb)}")

posters_dir = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1/frontend/public/posters")
jpg_count = len(list(posters_dir.glob("*.jpg")))
print(f"\nposters/ 实际文件: {jpg_count}")

# 有 jpg 但 JSON 里没 poster_local 的（需要补到 JSON）
jpg_ids = {f.stem for f in posters_dir.glob("*.jpg")}
json_ids = set(has_local.keys())
need_merge = jpg_ids - json_ids
print(f"JSON 里缺 poster_local 但磁盘有 jpg: {len(need_merge)} 部")
