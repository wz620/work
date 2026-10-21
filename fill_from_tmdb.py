"""用 TMDB API 补全 movie-details.json 里的文本详情（director, cast, overview, rating, runtime）。
海报因为 image.tmdb.org 被墙保持 39 张，前端自动 fallback。

用法：python fill_from_tmdb.py
"""
from __future__ import annotations
import json, time
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
DETAILS_JSON = ROOT / "frontend" / "public" / "movie-details.json"
API_BASE = "https://api.themoviedb.org/3"
TMDB_KEY = "61572be02f0a068658828f6396aacf60"  # 已验证可用

HEADERS = {"User-Agent": "Mozilla/5.0 CineLab-TMDB-Batch/1.0"}

# 1. 加载已有详情
details = json.loads(DETAILS_JSON.read_text(encoding="utf-8"))
print(f"已有 details: {len(details)} 条")

# 2. 从 API 拉 70 部电影的元数据（title, year）
s = requests.Session()
s.headers.update({"Origin": "http://127.0.0.1:8080", "Referer": "http://127.0.0.1:8080/"})

# 先登录拿 session cookie
r = s.get("http://127.0.0.1:8080/api/v1/auth/csrf", timeout=10)
csrf = r.json()["csrf_token"]
r = s.post("http://127.0.0.1:8080/api/v1/auth/login",
           data=json.dumps({"login_name": "testuser", "password": "thisisalongpw123"}),
           headers={"X-CSRF-Token": csrf, "Content-Type": "application/json"},
           timeout=10)
if r.status_code == 200 and r.json().get("csrf_token"):
    csrf = r.json()["csrf_token"]

# 跑所有算法拿 movie_id
all_movie_ids = set()
for algo in ["popular", "content", "itemcf", "als", "cold_start"]:
    for user in ["14", "55"]:
        url = f"http://127.0.0.1:8080/api/v1/demo/history-users/{user}/recommendations/{algo}"
        r = s.get(url, params={"limit": 10}, timeout=10)
        if r.status_code == 200:
            for it in r.json().get("items", []):
                all_movie_ids.add(int(it["movie_id"]))

print(f"目标电影: {len(all_movie_ids)} 部")

# 3. 从 Cinelab API 拿每部电影的 title/year
print("\n=== 拉 Cinelab 电影元数据 ===")
cinelab_meta = {}
for mid in sorted(all_movie_ids):
    r = s.get(f"http://127.0.0.1:8080/api/v1/movies/{mid}", timeout=10)
    if r.status_code == 200:
        cinelab_meta[mid] = r.json()

# 4. 用 TMDB API 补文本详情
print("\n=== TMDB 文本详情补全 ===")
updated_count = 0
for mid in sorted(all_movie_ids):
    meta = cinelab_meta.get(mid, {})
    title = meta.get("movielens_title") or meta.get("title_zh") or f"Movie {mid}"
    year = meta.get("release_year")

    key = str(mid)
    entry = details.get(key, {})

    # 检查是否需要补（director/imdb_rating 缺失视为需要）
    has_director = bool(entry.get("director"))
    has_imdb = bool(entry.get("imdb_rating"))
    if has_director and has_imdb:
        print(f"  #{mid} {title} — 已有详情，跳过")
        continue

    # TMDB search — 先清理 title（去掉括号年份、副标题）
    import re
    q = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
    # 处理带 " (aka ...)" 的别名
    q = re.sub(r"\s*\(aka\s+.*?\)", "", q, flags=re.I).strip()
    # 处理 "The Script, the Cast" 之类后缀
    q = q.replace(": The Script, the Cast", "").strip()
    search_params = {"query": q, "api_key": TMDB_KEY, "include_adult": "false"}
    if year:
        search_params["year"] = str(year)

    tmdb_id = None
    imdb_id = entry.get("imdb_id", "")

    if not imdb_id:
        try:
            r = requests.get(f"{API_BASE}/search/movie", params=search_params, headers=HEADERS, timeout=15)
            if r.status_code == 200 and r.json().get("results"):
                # 找最匹配的
                results = r.json()["results"]
                best = results[0]
                for res in results:
                    rt = res.get("release_date", "")[:4]
                    if year and rt == str(year):
                        best = res
                        break
                tmdb_id = best["id"]
                entry["omdb_title"] = best.get("title", "")
                entry["omdb_year"] = best.get("release_date", "")[:4]
        except Exception as e:
            print(f"  #{mid} TMDB search ERR: {e}")

    # TMDB detail
    if tmdb_id:
        try:
            r = requests.get(f"{API_BASE}/movie/{tmdb_id}", params={"api_key": TMDB_KEY}, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                dd = r.json()
                if dd.get("imdb_id"):
                    entry["imdb_id"] = dd["imdb_id"]
                entry["imdb_rating"] = str(round(dd.get("vote_average", 0), 1)) if dd.get("vote_average", 0) > 0 else ""
                entry["plot"] = dd.get("overview", "")[:500]
                entry["runtime"] = f"{dd.get('runtime', '')} min" if dd.get("runtime") else ""
                genres = dd.get("genres", [])
                # rated 没法从 TMDB 拿（需要额外 endpoint），留空
        except Exception as e:
            print(f"  #{mid} TMDB detail ERR: {e}")
        time.sleep(0.1)

        # TMDB credits
        try:
            r = requests.get(f"{API_BASE}/movie/{tmdb_id}/credits", params={"api_key": TMDB_KEY}, headers=HEADERS, timeout=15)
            if r.status_code == 200:
                cd = r.json()
                dirs = [c["name"] for c in cd.get("crew", []) if c.get("job") == "Director"]
                if dirs:
                    entry["director"] = ", ".join(dirs[:3])
                cast = [c["name"] for c in cd.get("cast", [])[:5]]
                if cast:
                    entry["actors"] = ", ".join(cast)
        except Exception as e:
            print(f"  #{mid} TMDB credits ERR: {e}")
        time.sleep(0.1)

    details[key] = entry
    updated_count += 1
    print(f"  #{mid} {title} ({year}) ✓ director={entry.get('director','?')[:25]} imdb={entry.get('imdb_rating','?')}")

# 5. 写回
DETAILS_JSON.write_text(json.dumps(details, indent=2, ensure_ascii=False), encoding="utf-8")

# 6. 统计
poster_count = len(list((ROOT / "frontend" / "public" / "posters").glob("*.jpg")))
with_detail = sum(1 for m in all_movie_ids if details.get(str(m), {}).get("director") or details.get(str(m), {}).get("imdb_rating"))
with_poster = sum(1 for m in all_movie_ids if (ROOT / "frontend" / "public" / "posters" / f"{m}.jpg").exists())

print(f"\n=== 完成 ===")
print(f"details.json: {len(details)} 条 (本次更新 {updated_count})")
print(f"目标: {len(all_movie_ids)} 部电影")
print(f"有文本详情覆盖: {with_detail}/{len(all_movie_ids)} ({with_detail*100//max(1,len(all_movie_ids))}%)")
print(f"有海报覆盖: {with_poster}/{len(all_movie_ids)} ({with_poster*100//max(1,len(all_movie_ids))}%)")
print(f"posters/ 目录: {poster_count} 张")
