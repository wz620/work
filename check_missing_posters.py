import json, requests

KEY = "61572be02f0a068658828f6396aacf60"
API = "https://api.themoviedb.org/3"

d = json.load(open("frontend/public/movie-details.json"))
no_poster = [(k, v) for k, v in d.items() if not v.get("poster_local")]
print(f"共 {len(no_poster)} 部缺海报\n")

# 从 TMDB detail 拿 poster_path + popularity 评分
import time
for key, v in no_poster:
    mid = int(key)
    title = v.get("omdb_title", "?")
    imdb_id = v.get("imdb_id", "")

    # 如果有 imdb_id，用 find_by_imdb 更准
    poster_path = ""
    if imdb_id:
        try:
            r = requests.get(f"{API}/find/{imdb_id}", params={"external_source": "imdb_id", "api_key": KEY}, timeout=10)
            if r.status_code == 200:
                results = r.json().get("movie_results", [])
                if results:
                    poster_path = results[0].get("poster_path", "")
                    popularity = results[0].get("popularity", 0)
                    print(f"  #{mid} {title} | imdb={imdb_id} | poster_path={poster_path} | pop={popularity:.1f}")
                    continue
        except Exception as e:
            print(f"  #{mid} find_by_imdb ERR: {e}")

    # fallback: search
    year = v.get("omdb_year", "")
    try:
        import re
        q = re.sub(r"\s*\(.*?\)\s*$", "", title).strip()
        r = requests.get(f"{API}/search/movie", params={"query": q, "year": year, "api_key": KEY}, timeout=10)
        if r.status_code == 200 and r.json().get("results"):
            m = r.json()["results"][0]
            poster_path = m.get("poster_path", "")
            print(f"  #{mid} {title} | poster_path={poster_path}")
        else:
            print(f"  #{mid} {title} | NO RESULTS poster_path=?")
    except Exception as e:
        print(f"  #{mid} search ERR: {e}")
    time.sleep(0.2)
