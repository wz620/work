"""给 movie-details.json 全部条目补 tmdb_poster_path（从 TMDB API 拿）。"""
import json, time, requests

KEY = "61572be02f0a068658828f6396aacf60"
API = "https://api.themoviedb.org/3"

ROOT = "e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1"
DETAILS_PATH = f"{ROOT}/frontend/public/movie-details.json"

d = json.load(open(DETAILS_PATH))
print(f"总条目: {len(d)}")

updated = 0
for key, v in d.items():
    if v.get("tmdb_poster_path"):
        continue  # 已有
    imdb_id = v.get("imdb_id", "")
    title = v.get("omdb_title", "")
    year = v.get("omdb_year", "")

    poster_path = ""
    if imdb_id and imdb_id.startswith("tt"):
        try:
            r = requests.get(f"{API}/find/{imdb_id}", params={"external_source": "imdb_id", "api_key": KEY}, timeout=15)
            if r.status_code == 200:
                results = r.json().get("movie_results", [])
                if results:
                    poster_path = results[0].get("poster_path", "")
        except Exception as e:
            print(f"  #{key} find_by_imdb ERR: {e}")
        time.sleep(0.3)

    if not poster_path and title:
        import re
        q = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
        try:
            r = requests.get(f"{API}/search/movie", params={"query": q, "year": year, "api_key": KEY}, timeout=15)
            if r.status_code == 200 and r.json().get("results"):
                poster_path = r.json()["results"][0].get("poster_path", "")
        except Exception as e:
            print(f"  #{key} search ERR: {e}")
        time.sleep(0.3)

    if poster_path:
        v["tmdb_poster_path"] = poster_path
        updated += 1
        print(f"  #{key} {title} ✓ {poster_path}")
    else:
        print(f"  #{key} {title} ✗ NO POSTER")

open(DETAILS_PATH, "w").write(json.dumps(d, indent=2, ensure_ascii=False))

has_poster = sum(1 for v in d.values() if v.get("poster_local") or v.get("tmdb_poster_path"))
has_local = sum(1 for v in d.values() if v.get("poster_local"))
has_tmdb = sum(1 for v in d.values() if v.get("tmdb_poster_path"))
print(f"\n=== 完成 ===")
print(f"  本地海报: {has_local}/70")
print(f"  TMDB poster_path: {has_tmdb}/70")
print(f"  覆盖总数: {has_poster}/70")
print(f"  本次更新: {updated}")
