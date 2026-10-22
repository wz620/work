"""尝试各种方式绕过 image.tmdb.org 的网络封锁下载海报。"""
import json, os, time, ssl, subprocess
from pathlib import Path
import requests

ROOT = "e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1"
POSTERS_DIR = Path(f"{ROOT}/frontend/public/posters")
DETAILS = json.load(open(f"{ROOT}/frontend/public/movie-details.json"))

# 找 31 部缺本地海报但有 tmdb_poster_path 的
need = [(k, v) for k, v in DETAILS.items() if not v.get("poster_local") and v.get("tmdb_poster_path")]
print(f"需下载: {len(need)} 张")

PROXIES = [
    ("direct", None, None),
    ("picin", lambda p: f"https://picin.pictures/https://image.tmdb.org{p}"),
    ("images.weserv.nl", lambda p: f"https://images.weserv.nl/?url=image.tmdb.org{p}"),
    ("fastly", lambda p: f"https://image.tmdb.org{p}".replace("image.tmdb.org", "image-tmdb.org")),
]

# 先测试各代理对第一张图的可达性
test_url = f"https://image.tmdb.org{need[0][1]['tmdb_poster_path']}"
print(f"\n测试目标: {test_url}")

results = {}
for name, _, url_fn in PROXIES:
    if url_fn:
        url = url_fn(need[0][1]["tmdb_poster_path"])
    else:
        url = test_url
    try:
        r = requests.get(url, timeout=15, verify=False, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
        size = len(r.content)
        results[name] = (r.status_code, size)
        print(f"  {name:25} → {r.status_code}, size={size}B")
    except Exception as e:
        results[name] = ("FAIL", str(e)[:40])
        print(f"  {name:25} → FAIL {str(e)[:40]}")

# 用成功的代理批量下载
working_proxy = None
for name, _, url_fn in PROXIES:
    if isinstance(results.get(name), tuple) and results[name][0] == 200 and results[name][1] > 5000:
        working_proxy = (name, url_fn)
        print(f"\n✓ 使用代理: {name}")
        break

if not working_proxy:
    print("\n✗ 所有代理都失败了，无法下载")
    exit(1)

name, url_fn = working_proxy
ok, fail = 0, 0
for key, v in need:
    dst = POSTERS_DIR / f"{key}.jpg"
    if dst.exists() and dst.stat().st_size > 5000:
        ok += 1
        continue
    url = url_fn(v["tmdb_poster_path"])
    try:
        r = requests.get(url, timeout=20, verify=False, headers={"User-Agent": "Mozilla/5.0 Chrome/120"})
        if r.status_code == 200 and len(r.content) > 5000:
            dst.write_bytes(r.content)
            DETAILS[key]["poster_local"] = f"/posters/{key}.jpg"
            ok += 1
            print(f"  ✓ #{key} {v.get('omdb_title','?')[:25]} {len(r.content)//1024}KB")
        else:
            fail += 1
            print(f"  ✗ #{key} status={r.status_code} size={len(r.content)}")
    except Exception as e:
        fail += 1
        print(f"  ✗ #{key} FAIL {type(e).__name__}")
    time.sleep(0.2)

open(f"{ROOT}/frontend/public/movie-details.json", "w").write(json.dumps(DETAILS, indent=2, ensure_ascii=False))

print(f"\n=== 完成 ===")
print(f"成功: {ok}, 失败: {fail}")
jps = list(POSTERS_DIR.glob("*.jpg"))
print(f"posters/ 目录: {len(jps)} 张")
with_poster = sum(1 for v in DETAILS.values() if v.get("poster_local"))
print(f"movie-details.json 有 poster_local: {with_poster}/70")
