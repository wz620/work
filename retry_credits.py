import requests, json, time

KEY = "61572be02f0a068658828f6396aacf60"
API = "https://api.themoviedb.org/3"

ROOT = "e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1"
DETAILS_PATH = f"{ROOT}/frontend/public/movie-details.json"

details = json.load(open(DETAILS_PATH))

fixes = {20: ("Money Train", 1995), 1396: ("Sneakers", 1992), 1639: ("Chasing Amy", 1997)}

for mid, (title, year) in fixes.items():
    key = str(mid)
    entry = details.get(key, {})
    print(f"#{mid} before: director={entry.get('director','?')} actors={entry.get('actors','?')[:30]}")

    r = requests.get(f"{API}/search/movie", params={"query": title, "year": str(year), "api_key": KEY}, timeout=15)
    tmdb_id = r.json()["results"][0]["id"]
    print(f"  tmdb_id={tmdb_id}")
    time.sleep(0.5)

    # credits with retry
    for attempt in range(3):
        try:
            r = requests.get(f"{API}/movie/{tmdb_id}/credits", params={"api_key": KEY}, timeout=30)
            if r.status_code == 200:
                cd = r.json()
                dirs = [c["name"] for c in cd.get("crew", []) if c.get("job") == "Director"]
                entry["director"] = ", ".join(dirs[:3]) if dirs else entry.get("director", "")
                cast = [c["name"] for c in cd.get("cast", [])[:5]]
                if cast:
                    entry["actors"] = ", ".join(cast)
                print(f"  ✓ director={entry.get('director','?')} cast={cast}")
                break
        except Exception as e:
            print(f"  attempt {attempt+1} fail: {e}")
            time.sleep(3)
    details[key] = entry

open(DETAILS_PATH, "w").write(json.dumps(details, indent=2, ensure_ascii=False))
print("\n已写回 movie-details.json")

# 最终统计
has_dir = sum(1 for v in details.values() if v.get("director"))
has_actor = sum(1 for v in details.values() if v.get("actors"))
has_imdb = sum(1 for v in details.values() if v.get("imdb_rating"))
print(f"director 覆盖: {has_dir}/70")
print(f"actors 覆盖: {has_actor}/70")
print(f"imdb_rating 覆盖: {has_imdb}/70")
