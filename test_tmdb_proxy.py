"""测 TMDB API 代理 + 批量匹配的可行性。"""
import requests, json

PROXIES = {"http": "http://127.0.0.1:7897", "https": "http://127.0.0.1:7897"}
KEY = "61572be02f0a068658828f6396aacf60"

# 1) API 是否通
r = requests.get(
    f"https://api.themoviedb.org/3/search/movie",
    params={"api_key": KEY, "query": "Toy Story", "year": 1995, "language": "en-US"},
    proxies=PROXIES, timeout=15,
)
print(f"search status={r.status_code}")
d = r.json()
print(f"found {d['total_results']}")
for m in d["results"][:3]:
    print(f"  tmdb_id={m['id']} year={m['release_date'][:4] if m['release_date'] else '?'} poster={m['poster_path']} title={m['title']}")

# 2) 直接 detail 拿 poster_path
r2 = requests.get(
    f"https://api.themoviedb.org/3/movie/862",
    params={"api_key": KEY, "language": "en-US"},
    proxies=PROXIES, timeout=15,
)
d2 = r2.json()
print(f"\ndetail 862: imdb_id={d2.get('imdb_id')} poster_path={d2.get('poster_path')}")

# 3) 测 image.tmdb.org 走代理下载
r3 = requests.get(
    f"https://image.tmdb.org/t/p/w342{d2.get('poster_path')}",
    proxies=PROXIES, timeout=20,
)
print(f"image status={r3.status_code} size={len(r3.content)//1024}KB")
