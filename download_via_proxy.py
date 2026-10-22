"""用 HTTP 代理下载剩余 31 张 TMDB 海报到本地。"""
import json, time, requests
from pathlib import Path

ROOT = Path("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1")
POSTERS_DIR = ROOT / "frontend/public/posters"
DETAILS_PATH = ROOT / "frontend/public/movie-details.json"

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
HEADERS = {"User-Agent": "Mozilla/5.0 Chrome/120"}

d = json.loads(DETAILS_PATH.read_text(encoding="utf-8"))
need = [(k, v) for k, v in d.items() if not v.get("poster_local") and v.get("tmdb_poster_path")]
print(f"需下载: {len(need)} 张\n")

ok, fail = 0, 0
for key, v in need:
    url = f"https://image.tmdb.org/t/p/w342{v['tmdb_poster_path']}"
    dst = POSTERS_DIR / f"{key}.jpg"
    if dst.exists() and dst.stat().st_size > 5000:
        print(f"  已存在 #{key}")
        ok += 1
        continue
    try:
        r = requests.get(url, headers=HEADERS, proxies=PROXIES, timeout=20)
        if r.status_code == 200 and len(r.content) > 5000:
            dst.write_bytes(r.content)
            d[key]["poster_local"] = f"/posters/{key}.jpg"
            print(f"  ✓ #{key} {v.get('omdb_title','?')[:25]} {len(r.content)//1024}KB")
            ok += 1
        else:
            print(f"  ✗ #{key} status={r.status_code} size={len(r.content)}")
            fail += 1
    except Exception as e:
        print(f"  ✗ #{key} FAIL {type(e).__name__}: {str(e)[:50]}")
        fail += 1
    time.sleep(0.3)

DETAILS_PATH.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

total_jpg = len(list(POSTERS_DIR.glob("*.jpg")))
with_poster = sum(1 for v in d.values() if v.get("poster_local"))
print(f"\n=== 完成 ===")
print(f"本次: 成功 {ok}, 失败 {fail}")
print(f"posters/ 目录: {total_jpg} 张")
print(f"movie-details.json 有 poster_local: {with_poster}/70")
