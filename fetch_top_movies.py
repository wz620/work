"""一次性收集所有算法 × 用户 Top-10 去重 movie_id，然后补全海报 + OMDb 详情。

用法：
    python fetch_top_movies.py
"""
from __future__ import annotations
import json, os, re, sys, time, urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
FRONTEND_PUBLIC = ROOT / "frontend" / "public"
POSTERS_DIR = FRONTEND_PUBLIC / "posters"
DETAILS_JSON = FRONTEND_PUBLIC / "movie-details.json"

API_BASE = "http://127.0.0.1:8080/api/v1"
OMDB_KEY = "9a1e1d7c"  # 免费 key

ALGORITHMS = ["popular", "content", "itemcf", "als", "cold_start"]
USERS = ["ml:14", "ml:55"]

POSTERS_DIR.mkdir(parents=True, exist_ok=True)

import requests

s = requests.Session()
s.headers.update({"Origin": "http://127.0.0.1:8080", "Referer": "http://127.0.0.1:8080/"})

# ========== 1. 拿 csrf + 登录（用 session cookie，不是 bearer token）==========
r = s.get(f"{API_BASE}/auth/csrf", timeout=10)
csrf = r.json()["csrf_token"]
print(f"csrf GET: {r.status_code}")

# 先尝试登录 testuser；不行就注册
def do_login(user, pw):
    global csrf
    r = s.post(f"{API_BASE}/auth/login",
               data=json.dumps({"login_name": user, "password": pw}),
               headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
               timeout=10)
    if r.status_code == 200 and r.json().get("csrf_token"):
        csrf = r.json()["csrf_token"]
    return r

for user, pw in [("testuser", "thisisalongpw123"), ("123", "abcdefghijkl")]:
    r = do_login(user, pw)
    print(f"login {user}: {r.status_code}", r.text[:80])
    if r.status_code == 200:
        break
else:
    # 注册新账号
    r = s.post(f"{API_BASE}/auth/register",
               data=json.dumps({"login_name": "newuser99", "password": "thisisalongpw999"}),
               headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
               timeout=10)
    print(f"register: {r.status_code}", r.text[:80])
    if r.json().get("csrf_token"):
        csrf = r.json()["csrf_token"]
    r = do_login("newuser99", "thisisalongpw999")
    print(f"re-login newuser99: {r.status_code}", r.text[:80])

print("session cookies:", dict(s.cookies))

# ========== 2. 收集所有 Top-10 movie_id ==========
all_movies: set[int] = set()
per_algo: dict[str, list[int]] = {}

for algo in ALGORITHMS:
    for user in USERS:
        # ml_user_id 要去掉 ml: 前缀
        ml_uid = user.replace("ml:", "")
        url = f"{API_BASE}/demo/history-users/{ml_uid}/recommendations/{algo}"
        r = s.get(url, params={"limit": 10}, timeout=10)
        if r.status_code != 200:
            print(f"  SKIP {algo} {user}: {r.status_code} {r.text[:120]}")
            continue
        data = r.json()
        items = data.get("items", [])
        mids = [it["movie_id"] for it in items]
        per_algo.setdefault(algo, []).extend(mids)
        all_movies.update(mids)
        print(f"  {algo:12} {user:6} → {len(mids)} movies")

print(f"\n去重后总共 {len(all_movies)} 部")
for algo in ALGORITHMS:
    uniq = sorted(set(per_algo.get(algo, [])))
    print(f"  {algo:12}: {len(uniq)} movies — {uniq}")

# ========== 3. 加载已有 ==========
existing_details = json.loads(DETAILS_JSON.read_text(encoding="utf-8")) if DETAILS_JSON.exists() else {}
existing_posters = {int(p.stem) for p in POSTERS_DIR.glob("*.jpg")}
print(f"\n已有 details: {len(existing_details)}, posters: {len(existing_posters)}")

# ========== 4. 拿电影元数据 ==========
print("\n=== 拉电影元数据 ===")
movies_meta: dict[int, dict] = {}
for mid in sorted(all_movies):
    r = s.get(f"{API_BASE}/movies/{mid}", timeout=10)
    if r.status_code == 200:
        movies_meta[mid] = r.json()

# ========== 5. 下载 OMDb + 海报 ==========
print("\n=== OMDb + 海报 ===")
headers = {"User-Agent": "Mozilla/5.0 CineLab-Batch/1.0"}

def fetch_omdb(title, year):
    q = {"t": title, "apikey": OMDB_KEY}
    if year:
        q["y"] = str(year)
    url = "https://www.omdbapi.com/?" + urllib.parse.urlencode(q)
    try:
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code != 200:
            return None
        d = r.json()
        if d.get("Response") == "True":
            return d
        clean = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
        if clean != title:
            q["t"] = clean
            r2 = requests.get("https://www.omdbapi.com/?" + urllib.parse.urlencode(q), headers=headers, timeout=15)
            if r2.status_code == 200 and r2.json().get("Response") == "True":
                return r2.json()
        return None
    except Exception as e:
        print(f"  OMDb error: {e}")
        return None

def download_poster(url, dst):
    if dst.exists() and dst.stat().st_size > 500:
        return True
    try:
        r = requests.get(url, headers=headers, timeout=30, stream=True)
        if r.status_code == 200 and int(r.headers.get("Content-Length", "0")) > 500:
            dst.write_bytes(r.content)
            return True
    except Exception:
        pass
    return False

new_details = dict(existing_details)
for mid in sorted(all_movies):
    meta = movies_meta.get(mid, {})
    title = meta.get("movielens_title") or meta.get("title_zh") or f"Movie {mid}"
    year = meta.get("release_year")
    key = str(mid)
    already_have = key in existing_details and mid in existing_posters
    if already_have:
        continue
    print(f"  #{mid} {title} ({year})")
    omdb = fetch_omdb(title, year)
    time.sleep(0.25)
    d = new_details.get(key, {})
    if omdb:
        d.update({
            "director": omdb.get("Director", ""),
            "actors": omdb.get("Actors", ""),
            "plot": omdb.get("Plot", ""),
            "rated": omdb.get("Rated", ""),
            "runtime": omdb.get("Runtime", ""),
            "imdb_rating": omdb.get("imdbRating", ""),
            "imdb_id": omdb.get("imdbID", ""),
            "omdb_title": omdb.get("Title", ""),
            "omdb_year": omdb.get("Year", ""),
        })
        poster_url = omdb.get("Poster", "")
        if poster_url.startswith("http"):
            dst = POSTERS_DIR / f"{mid}.jpg"
            if download_poster(poster_url, dst):
                d["poster_local"] = f"/posters/{mid}.jpg"
                print(f"    ✓ poster {dst.stat().st_size//1024}KB")
    new_details[key] = d

# ========== 6. 写回 ==========
DETAILS_JSON.write_text(json.dumps(new_details, indent=2, ensure_ascii=False), encoding="utf-8")
poster_count = len(list(POSTERS_DIR.glob("*.jpg")))
print(f"\n=== 完成 ===")
print(f"details.json: {len(new_details)} 条")
print(f"posters/: {poster_count} 张")
print(f"目标: {len(all_movies)} 部电影")
print(f"有详情覆盖: {sum(1 for m in all_movies if str(m) in new_details)}")
print(f"有海报覆盖: {sum(1 for m in all_movies if m in existing_posters or (POSTERS_DIR / f'{m}.jpg').exists())}")
