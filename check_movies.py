import requests
d = requests.get("http://127.0.0.1:8080/api/v1/movies?per_page=5").json()
print("=== 默认排序前 5 ===")
for m in d['items']:
    print(f"  id={m['movie_id']} rating_count={m.get('rating_count','?')} avg={m.get('average_rating','?')} {m['movielens_title'][:35]}")

print("\n=== page=1 ===")
d1 = requests.get("http://127.0.0.1:8080/api/v1/movies?per_page=12").json()
ids_page1 = [str(m['movie_id']) for m in d1['items']]

print("\n=== JSON 有 poster_local 的 id 范围 ===")
import json
d2 = json.loads(open("e:/实验/CineLab-Student-Windows-1.3.0-rc1/CineLab-Student-Windows-1.3.0-rc1/frontend/public/movie-details.json", encoding="utf-8").read())
has = set(d2.keys())

on_page1_with_poster = [mid for mid in ids_page1 if mid in has]
print(f"第 1 页 12 部里有海报: {len(on_page1_with_poster)}/12")
print(f"第 1 页 movie_id: {ids_page1}")
print(f"有海报的 id: {sorted([int(k) for k in has])[:20]}...")
